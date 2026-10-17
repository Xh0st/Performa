# Auth Testing Playbook
1. MongoDB: db.users.find({role:"admin"}) — bcrypt hash starts with $2b$; unique index on users.email.
2. API: curl -c cookies.txt -X POST $API/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@serviceauto.ro","password":"Admin2026!"}'
   then curl -b cookies.txt $API/api/auth/me
3. 5 failed logins for same ip+email -> 429 lockout 15 min.
4. Role gating: e.g. casier cannot GET /api/stock-like endpoints (/api/nirs -> 403); mecanic cannot GET /api/invoices (403).
