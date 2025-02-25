from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.openapi.models import OAuthFlowPassword
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from .models import Base, User, LoginHistory
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional, List
from .config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from .postgres import async_session, engine, get_session
from jose import jwt
import httpx
from .config import YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET, YANDEX_REDIRECT_URL

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

app = FastAPI()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.on_event("startup")
async def startup_event():
    await create_tables()

class RegisterRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class TelegramRequest(BaseModel):
    telegram_username: str

def create_tokens(email: str, role: str):
    access_payload = {"sub": email, "role": role, "exp": datetime.utcnow() + timedelta(minutes=int(ACCESS_TOKEN_EXPIRE_MINUTES))}
    refresh_payload = {"sub": email, "exp": datetime.utcnow() + timedelta(days=7)}
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)
    return access_token, refresh_token

@app.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_session)):
    user = User(email=request.email, password=pwd_context.hash(request.password))
    session.add(user)
    await session.commit()
    return {"access_token": "", "token_type": "bearer"}

@app.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).filter(User.email == form_data.username))
    user = result.scalars().first()
    if not user or not pwd_context.verify(form_data.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token, refresh_token = create_tokens(user.email, user.role)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/refresh", response_model=TokenResponse)
async def refresh(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        return {"access_token": create_tokens(email, "user")[0], "token_type": "bearer"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")

@app.get("/my_loginHistory")
async def my_login_history(token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    email = payload.get("sub")
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    history = await session.execute(select(LoginHistory).where(LoginHistory.user_id == user.id))
    return history.scalars().all()

@app.get("/users_loginHistory")
async def users_login_history(q: int, token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    email = payload.get("sub")
    user = await session.execute(select(User).where(User.email == email))
    user = user.scalars().first()
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    history = await session.execute(select(LoginHistory).where(LoginHistory.user_id == q))
    return history.scalars().all()

def get_yandex_auth_url():
    return (
        "https://oauth.yandex.ru/authorize?"
        "response_type=code&"
        f"client_id={YANDEX_CLIENT_ID}&"
        f"redirect_uri={YANDEX_REDIRECT_URL}"
    )

async def exchange_code_for_token(code: str):
    url = "https://oauth.yandex.ru/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": YANDEX_CLIENT_ID,
        "client_secret": YANDEX_CLIENT_SECRET,
        "redirect_uri": YANDEX_REDIRECT_URL
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=data)
        response.raise_for_status()  
        return response.json()

async def get_yandex_user_info(access_token: str):
    url = "https://api.yandex.ru/user_info"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()  
        return response.json()

@app.get("/yandex/")
async def auth_yandex():
    return RedirectResponse(get_yandex_auth_url())

@app.get("/yandex/callback")
async def auth_yandex_callback(code: str):
    token_data = await exchange_code_for_token(code)
    access_token = token_data['access_token']
    user_info = await get_yandex_user_info(access_token)
    email = user_info['email']
    role = "user"  
    access_token, refresh_token = create_tokens(email, role)
    return TokenResponse(access_token=access_token, token_type="bearer")

@app.post("/add_telegram")
async def add_telegram(request: TelegramRequest, token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    email = payload.get("sub")
    user = await session.execute(select(User).where(User.email == email))
    user = user.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.telegram_username = request.telegram_username
    await session.commit()
    return {"message": "Telegram username updated"}

