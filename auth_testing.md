# Auth Testing

## Credentials
- Admin: admin@mirrorstream.com / Admin@1234 (role: admin)
- Register a new user via /api/auth/register for a normal 'user' role.

## Flow
1. POST /api/auth/login {email,password} -> returns {access_token, user}. Token also set as cookie.
2. Send `Authorization: Bearer <token>` for all protected routes.
3. GET /api/auth/me -> current user.

## Notes
- bcrypt hashes start with $2b$.
- 5 failed logins within window -> 429 lockout for 15 min (per ip:email).
