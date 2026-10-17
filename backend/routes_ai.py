import os
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
from core import db, ser, oid, iso, require

router = APIRouter(prefix="/api")

PROMPTS = {
    "advisor": ("Ești AI Service Advisor într-un service auto din România. Pe baza vehiculului, kilometrajului și istoricului "
                "de intervenții, recomanzi lucrări (revizii, piese de uzură, verificări), estimezi ore de manoperă (normă) și costuri "
                "orientative în RON fără TVA, cu prioritate (urgent / recomandat / opțional). Răspunde structurat, concis, în markdown."),
    "obd": ("Ești AI Diagnostic Assistant pentru un service auto. Analizezi coduri OBD-II/DTC (ex. P0300) și simptome, explici cauzele "
            "probabile ordonate după probabilitate, pașii de diagnostic, piesele implicate și reparațiile sugerate cu timp estimat. "
            "Răspunde structurat, concis, în markdown."),
}


class AskIn(BaseModel):
    mode: str = "advisor"
    message: str
    vehicle_id: str = ""
    lang: str = "ro"


async def vehicle_context(vid: str) -> str:
    if not vid:
        return ""
    v = await db.vehicles.find_one({"_id": oid(vid)})
    if not v:
        return ""
    ctx = (f"Vehicul: {v['make']} {v['model']} {v.get('year', '')}, motor {v.get('engine', '')}, {v.get('power_kw', '')} kW, "
           f"{v.get('fuel', '')}, Euro {v.get('euro', '')}, {v.get('mileage', 0)} km, VIN {v['vin']}.\nIstoric intervenții:\n")
    async for w in db.work_orders.find({"vehicle_id": vid}, {"number": 1, "created_at": 1, "mileage_in": 1, "complaint": 1, "lines": 1}).sort("created_at", -1).limit(10):
        items = ", ".join(ln["description"] for ln in w.get("lines", []))
        ctx += f"- {w['created_at'][:10]} @ {w.get('mileage_in', '')} km: {w.get('complaint', '')} → {items}\n"
    return ctx


@router.post("/ai/stream")
async def ai_stream(body: AskIn, user=Depends(require("ai"))):
    if body.mode not in PROMPTS or not body.message.strip():
        raise HTTPException(400, "Cerere invalidă")
    ctx = await vehicle_context(body.vehicle_id)
    lang = "Răspunde în limba română." if body.lang == "ro" else "Answer in English."
    chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=str(uuid.uuid4()),
                   system_message=f"{PROMPTS[body.mode]} {lang}").with_model("gemini", "gemini-3.1-pro-preview")
    prompt = f"{ctx}\nÎntrebare: {body.message}" if ctx else body.message

    async def gen():
        answer = ""
        try:
            async for ev in chat.stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    answer += ev.content
                    yield ev.content
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:
            yield f"\n\n[Eroare AI: {e}]"
        await db.ai_messages.insert_one({"user_id": user["id"], "mode": body.mode, "vehicle_id": body.vehicle_id,
                                         "question": body.message, "answer": answer, "at": iso()})

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/ai/history")
async def ai_history(user=Depends(require("ai"))):
    return [ser(m) for m in await db.ai_messages.find({"user_id": user["id"]}).sort("at", -1).to_list(30)]
