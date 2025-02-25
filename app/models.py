from sqlalchemy import Column, Integer, String, Text, ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(Text, unique=True, nullable=False)
    password = Column(Text, nullable=True)
    telegram_username = Column(Text, unique=True, nullable=True)
    role = Column(String, nullable=False, default='user')
    
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete")


class LoginHistory(Base):
    __tablename__ = "login_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(TIMESTAMP, server_default=func.now())
    
    user = relationship("User", back_populates="login_history")
