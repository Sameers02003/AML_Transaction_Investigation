import uuid, bcrypt, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from app.core.config import settings
from app.core.db import get_db
from app.models import User

bearer = HTTPBearer()
READ = ("analyst", "senior_investigator", "compliance_officer", "administrator", "auditor")
WORK = ("analyst", "senior_investigator", "compliance_officer", "administrator")   # auditor is read-only

def verify_pw(p, h): return bcrypt.checkpw(p.encode(), h.encode())
def make_token(u):
    return jwt.encode({"sub": str(u.id), "role": u.role, "exp": datetime.now(timezone.utc) + timedelta(hours=8)},
                      settings.jwt_secret, algorithm="HS256")

def current_user(creds=Depends(bearer), db=Depends(get_db)):
    try:
        data = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")
    u = db.get(User, uuid.UUID(data["sub"]))
    if not u or not u.active:
        raise HTTPException(401, "inactive user")
    return u

def require(*roles):
    def dep(u=Depends(current_user)):
        if u.role not in roles:
            raise HTTPException(403, "insufficient role")
        return u
    return dep