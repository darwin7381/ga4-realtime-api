from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from datetime import datetime
from typing import Optional

class User(Base):
    """用戶模型"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
    ga4_property_id = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True, nullable=False)
    
    # 關聯
    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")
    api_usage_logs = relationship("ApiUsageLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.name}')>"

class OAuthToken(Base):
    """OAuth Token 模型"""
    __tablename__ = "oauth_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    scope = Column(Text, nullable=True)
    token_type = Column(String(50), default="Bearer", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_revoked = Column(Boolean, default=False, nullable=False)
    
    # 關聯
    user = relationship("User", back_populates="oauth_tokens")
    
    # 索引
    __table_args__ = (
        Index('ix_oauth_tokens_user_id_active', 'user_id', 'is_revoked'),
        Index('ix_oauth_tokens_expires_at', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<OAuthToken(id={self.id}, user_id={self.user_id}, expires_at='{self.expires_at}')>"
    
    @property
    def is_expired(self) -> bool:
        """檢查 token 是否已過期"""
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)

class ApiUsageLog(Base):
    """API 使用記錄模型"""
    __tablename__ = "api_usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 可為空，支援 API Key 用戶
    api_key_user = Column(String(50), nullable=True)  # API Key 模式的用戶名
    endpoint = Column(String(100), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=True)
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)  # 支援 IPv6
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 關聯
    user = relationship("User", back_populates="api_usage_logs")
    
    # 索引
    __table_args__ = (
        Index('ix_api_usage_logs_user_id_created', 'user_id', 'created_at'),
        Index('ix_api_usage_logs_api_key_user_created', 'api_key_user', 'created_at'),
        Index('ix_api_usage_logs_endpoint_created', 'endpoint', 'created_at'),
        Index('ix_api_usage_logs_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<ApiUsageLog(id={self.id}, endpoint='{self.endpoint}', status={self.status_code})>"

class GoogleAnalyticsProperty(Base):
    """Google Analytics Property 模型（支援多個 GA4 屬性）"""
    __tablename__ = "ga4_properties"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    property_id = Column(String(50), nullable=False)
    property_name = Column(String(200), nullable=True)
    website_url = Column(String(500), nullable=True)
    industry_category = Column(String(100), nullable=True)
    time_zone = Column(String(50), nullable=True)
    currency_code = Column(String(10), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 關聯
    user = relationship("User", backref="ga4_properties")
    
    # 索引
    __table_args__ = (
        Index('ix_ga4_properties_user_id_active', 'user_id', 'is_active'),
        Index('ix_ga4_properties_property_id', 'property_id'),
    )
    
    def __repr__(self):
        return f"<GoogleAnalyticsProperty(id={self.id}, property_id='{self.property_id}', name='{self.property_name}')>"

class UserApiKey(Base):
    """用戶 API Key 模型"""
    __tablename__ = "user_api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("ga4_properties.id"), nullable=True)  # 關聯的 GA4 屬性
    key_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    api_key = Column(String(64), unique=True, nullable=False)  # 生成的 API Key
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # 關聯
    user = relationship("User", backref="api_keys")
    property = relationship("GoogleAnalyticsProperty", backref="api_keys")
    
    # 索引
    __table_args__ = (
        Index('ix_user_api_keys_user_id_active', 'user_id', 'is_active'),
        Index('ix_user_api_keys_api_key', 'api_key'),
        Index('ix_user_api_keys_property_id', 'property_id'),
    )
    
    def __repr__(self):
        return f"<UserApiKey(id={self.id}, key_name='{self.key_name}', user_id={self.user_id}, property_id={self.property_id})>" 