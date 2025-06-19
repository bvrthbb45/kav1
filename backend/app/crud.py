from sqlalchemy import func, cast, String
from sqlalchemy.orm import Session
from . import models


def get_visitors(db: Session):
    return db.query(models.Visitor).all()


def get_visitors_inside(db: Session):
    return db.query(models.Visitor).filter(models.Visitor.inside).all()


def create_visitor(db: Session, name: str, visitorid: str, properties: dict):
    db_visitor = models.Visitor(
        name=name, visitorid=visitorid, inside=False, properties=properties
    )
    db.add(db_visitor)
    db.commit()
    db.refresh(db_visitor)

    log_visitor_action(db, db_visitor.dbid, "creation")

    return db_visitor


def update_visitor_status(db: Session, visitor_id: str, is_inside: bool):
    visitor = (
        db.query(models.Visitor).filter(models.Visitor.visitorid == visitor_id).first()
    )

    if visitor:
        visitor.inside = is_inside
        db.commit()
        db.refresh(visitor)
        log_visitor_action(db, visitor.dbid, "entry" if is_inside else "exit")
        return visitor
    return None


def delete_visitor(db: Session, visitor_id: str):
    visitor = (
        db.query(models.Visitor).filter(models.Visitor.visitorid == visitor_id).first()
    )

    if visitor:
        visitor_data = {"visitorid": visitor.visitorid, "name": visitor.name}
        db.delete(visitor)
        db.commit()
        return visitor_data
    return None


def get_visitor_by_id(db: Session, visitor_id: str):
    return (
        db.query(models.Visitor).filter(models.Visitor.visitorid == visitor_id).first()
    )


def get_visitor_by_dbid(db: Session, visitor_dbid: int):
    return db.query(models.Visitor).filter(models.Visitor.dbid == visitor_dbid).first()


def search_visitors_by_name(db: Session, search_query: str):
    return (
        db.query(models.Visitor)
        .filter(models.Visitor.name.ilike(f"%{search_query}%"))
        .all()
    )


def log_visitor_action(db: Session, visitor_dbid: int, action: str):
    log = models.VisitorLog(
        visitor_dbid=visitor_dbid,
        action=action,
    )
    db.add(log)
    db.commit()
    db.refresh(log)


def get_latest_log_for_visitor(db: Session, visitor_dbid: int):
    return (
        db.query(models.VisitorLog)
        .filter(models.VisitorLog.visitor_dbid == visitor_dbid)
        .order_by(models.VisitorLog.timestamp.desc())
        .first()
    )


def get_logs(db: Session, limit: int = 20):
    return (
        db.query(models.VisitorLog)
        .order_by(models.VisitorLog.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_logs_for_visitor(db: Session, visitorid: str):
    visitor = (
        db.query(models.Visitor).filter(models.Visitor.visitorid == visitorid).first()
    )
    if not visitor:
        return []

    logs = (
        db.query(models.VisitorLog)
        .filter(models.VisitorLog.visitor_dbid == visitor.dbid)
        .order_by(models.VisitorLog.timestamp.desc())
        .all()
    )

    result = []
    for log in logs:
        log_dict = {k: v for k, v in log.__dict__.items() if k != "_sa_instance_state"}
        log_dict["visitor_name"] = visitor.name
        result.append(log_dict)

    return result


def search_visitors_by_key_value(db: Session, key: str, value: str = None):
    query = db.query(models.Visitor)
    json_path = f"$.{key}"

    if value is None:
        query = query.filter(
            func.json_extract(models.Visitor.properties, json_path) != None
        )
    else:
        query = query.filter(
            cast(func.json_extract(models.Visitor.properties, json_path), String)
            == value
        )
    return query.all()


def update_visitor_details(
    db: Session,
    visitor_id: str,
    name: str = None,
    visitorid: str = None,
    properties: dict = None,
):
    visitor = (
        db.query(models.Visitor).filter(models.Visitor.visitorid == visitor_id).first()
    )

    if visitor:
        if name is not None:
            visitor.name = name
        if visitorid is not None:
            visitor.visitorid = visitorid
        if properties is not None:
            visitor.properties = properties
        db.commit()
        db.refresh(visitor)
        log_visitor_action(db, visitor.dbid, "update")
        return visitor
    return None
