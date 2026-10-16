from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    JSON,
    ForeignKey,
    DateTime,
    Index,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Visitor(Base):
    __tablename__ = "visitors"

    dbid = Column("dbid", Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    visitorid = Column(String, unique=True, index=True, nullable=False)
    inside = Column(Boolean, default=False, nullable=False)
    properties = Column("properties", JSON, nullable=True)

    logs = relationship("VisitorLog", back_populates="visitor", cascade="all, delete")


class VisitorLog(Base):
    __tablename__ = "visitor_logs"
    # create_all() only adds these on NEW databases. Existing installs get them
    # from tools/fix_02_add_indexes.py (same names).
    __table_args__ = (
        Index("ix_visitor_logs_visitor_dbid_timestamp", "visitor_dbid", "timestamp"),
        Index("ix_visitor_logs_timestamp", "timestamp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    visitor_dbid = Column(
        Integer, ForeignKey("visitors.dbid", ondelete="CASCADE"), nullable=False
    )
    action = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.now)

    visitor = relationship("Visitor", back_populates="logs")
