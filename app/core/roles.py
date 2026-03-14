from fastapi import Depends, HTTPException
from app.core.security import get_current_user
# from app.models.ngo import NGO
# from app.core.security import get_db

def user_required(user = Depends(get_current_user)):
    if user.role != "user":
        raise HTTPException(status_code=403, detail="User access required")
    return user

def ngo_required(user=Depends(get_current_user)):
    if user.role != "ngo":
        raise HTTPException(status_code=403, detail="NGO access required")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="NGO not approved")
    # ngo = db.query(NGO).filter(NGO.email == user.email).first()
    # if not ngo:
    #     raise HTTPException(status_code=404, detail="NGO profile not found")
    #
    # return ngo
    return user


def admin_required(user = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
