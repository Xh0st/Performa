import { useEffect, useState } from "react";
import { toast } from "sonner";

import { api, errMsg, useApi } from "@/lib/api";
import { useLang } from "@/lib/prefs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect } from "@/components/common";


const CASH_METHOD = "numerar";
const CASHLESS_METHODS = ["pos", "transfer"];


export function PaymentEntryForm({ cashOnly = false, onSaved }) {
  const { tr } = useLang();
  const { data: clients } = useApi("/clients");
  const [clientId, setClientId] = useState("");
  const [invoiceId, setInvoiceId] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState(cashOnly ? CASH_METHOD : "pos");
  const [cashDocument, setCashDocument] = useState("receipt");
  const [reference, setReference] = useState("");
  const [saving, setSaving] = useState(false);
  const { data: invoicesData } = useApi(
    clientId ? `/clients/${clientId}/invoices?page=1&page_size=100` : null,
  );
  const client = (clients || []).find((item) => item.id === clientId);
  const invoices = (invoicesData?.items || [])
    .filter((invoice) => invoice.type === "fiscal" && invoice.status !== "paid" && invoice.kind !== "credit_note")
    .map((invoice) => ({
      ...invoice,
      due: invoice.totals.gross - invoice.paid_amount - (invoice.credited_amount || 0),
    }))
    .sort((left, right) => String(left.due_date).localeCompare(String(right.due_date)));

  useEffect(() => {
    if (cashOnly) setMethod(CASH_METHOD);
  }, [cashOnly]);

  const save = async () => {
    setSaving(true);
    try {
      const response = await api.post("/payments", {
        client_id: clientId,
        invoice_id: invoiceId,
        amount: Number(amount),
        method,
        cash_document: cashDocument,
        reference,
      });
      toast.success(tr("Încasare înregistrată", "Payment recorded"));
      if (cashOnly && ["chitanta", "bon_fiscal"].includes(response.data.doc_type)) {
        window.open(`/print/receipt/${response.data.id}`, "_blank", "noopener,noreferrer");
      }
      setInvoiceId("");
      setAmount("");
      setReference("");
      onSaved();
    } catch (error) {
      toast.error(errMsg(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-3 border-b border-border pb-5 lg:grid-cols-4">
      <Field label={tr("Client", "Client")}>
        <NativeSelect
          data-testid={`payment-entry-${cashOnly ? "cash" : "cashless"}-client-select`}
          value={clientId}
          onChange={(event) => {
            setClientId(event.target.value);
            setInvoiceId("");
            setCashDocument("receipt");
          }}
        >
          <option value="">{tr("Selectează clientul", "Select client")}</option>
          {(clients || []).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </NativeSelect>
      </Field>
      <Field label={tr("Factura restantă", "Outstanding invoice")}>
        <NativeSelect
          data-testid={`payment-entry-${cashOnly ? "cash" : "cashless"}-invoice-select`}
          value={invoiceId}
          disabled={!clientId}
          onChange={(event) => setInvoiceId(event.target.value)}
        >
          <option value="">{tr("FIFO automat", "Automatic FIFO")}</option>
          {invoices.map((invoice) => (
            <option key={invoice.id} value={invoice.id}>
              {invoice.series}{invoice.number} · {invoice.due.toFixed(2)} RON
            </option>
          ))}
        </NativeSelect>
      </Field>
      {!cashOnly && (
        <Field label={tr("Metodă", "Method")}>
          <NativeSelect
            data-testid="payment-entry-cashless-method-select"
            value={method}
            onChange={(event) => setMethod(event.target.value)}
          >
            <option value="pos">{tr("Card POS", "Card POS")}</option>
            <option value="transfer">{tr("Ordin de plată", "Bank transfer")}</option>
          </NativeSelect>
        </Field>
      )}
      {cashOnly && (
        <Field label={tr("Document numerar", "Cash document")}>
          <NativeSelect
            data-testid="payment-entry-cash-document-select"
            value={cashDocument}
            onChange={(event) => setCashDocument(event.target.value)}
          >
            <option value="receipt">{tr("Chitanță", "Receipt")}</option>
            {client?.type === "pf" && <option value="fiscal_receipt">{tr("Bon fiscal", "Fiscal receipt")}</option>}
            <option value="collection_order">{tr("Dispoziție de încasare", "Collection order")}</option>
          </NativeSelect>
        </Field>
      )}
      <Field label={tr("Sumă (RON)", "Amount (RON)")}>
        <Input
          data-testid={`payment-entry-${cashOnly ? "cash" : "cashless"}-amount-input`}
          type="number"
          min="0.01"
          step="0.01"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
      </Field>
      <Field label={tr("Referință", "Reference")}>
        <Input
          data-testid={`payment-entry-${cashOnly ? "cash" : "cashless"}-reference-input`}
          value={reference}
          onChange={(event) => setReference(event.target.value)}
        />
      </Field>
      <div className="flex items-end">
        <Button
          data-testid={`payment-entry-${cashOnly ? "cash" : "cashless"}-save-button`}
          disabled={saving || !clientId || !amount}
          onClick={save}
        >
          {tr("Înregistrează", "Record")}
        </Button>
      </div>
    </div>
  );
}


export function CashDepositForm({ available, onSaved }) {
  const { tr } = useLang();
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/cash-register/deposits", { amount: Number(amount), reference });
      toast.success(tr("Depunere bancară înregistrată", "Bank deposit recorded"));
      setAmount("");
      setReference("");
      onSaved();
    } catch (error) {
      toast.error(errMsg(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-border pt-4">
      <div className="text-sm text-muted-foreground">
        {tr("Disponibil în casă", "Cash available")}: <span className="font-mono">{available.toFixed(2)} RON</span>
      </div>
      <Field label={tr("Sumă depusă", "Deposit amount")}>
        <Input
          data-testid="cash-deposit-amount-input"
          className="w-40"
          type="number"
          min="0.01"
          step="0.01"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
        />
      </Field>
      <Field label={tr("Referință bancă", "Bank reference")}>
        <Input
          data-testid="cash-deposit-reference-input"
          className="w-52"
          value={reference}
          onChange={(event) => setReference(event.target.value)}
        />
      </Field>
      <Button data-testid="cash-deposit-save-button" disabled={saving || !amount} onClick={save}>
        {tr("Depune la bancă", "Deposit to bank")}
      </Button>
    </div>
  );
}


export function CashPayoutForm({ available, onSaved }) {
  const { tr } = useLang();
  const [kind, setKind] = useState("expense_settlement");
  const [beneficiary, setBeneficiary] = useState("");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");

  const save = async () => {
    try {
      await api.post("/cash-register/payouts", {
        kind,
        beneficiary,
        amount: Number(amount),
        reference,
      });
      toast.success(tr("Plată înregistrată", "Payout recorded"));
      setBeneficiary("");
      setAmount("");
      setReference("");
      onSaved();
    } catch (error) {
      toast.error(errMsg(error));
    }
  };

  return (
    <div className="grid gap-3 lg:grid-cols-5">
      <Field label={tr("Document", "Document")}>
        <NativeSelect data-testid="cash-payout-kind-select" value={kind} onChange={(event) => setKind(event.target.value)}>
          <option value="expense_settlement">{tr("Decont cheltuieli", "Expense settlement")}</option>
          <option value="payment_order">{tr("Dispoziție de plată", "Payment order")}</option>
        </NativeSelect>
      </Field>
      <Field label={tr("Beneficiar", "Beneficiary")}><Input data-testid="cash-payout-beneficiary-input" value={beneficiary} onChange={(event) => setBeneficiary(event.target.value)} /></Field>
      <Field label={tr("Sumă (RON)", "Amount (RON)")}><Input data-testid="cash-payout-amount-input" type="number" min="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} /></Field>
      <Field label={tr("Referință", "Reference")}><Input data-testid="cash-payout-reference-input" value={reference} onChange={(event) => setReference(event.target.value)} /></Field>
      <div className="flex items-end"><Button data-testid="cash-payout-save-button" disabled={!beneficiary || !amount || Number(amount) > available} onClick={save}>{tr("Înregistrează", "Record")}</Button></div>
    </div>
  );
}