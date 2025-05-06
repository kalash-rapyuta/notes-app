from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy import String, ForeignKey, DateTime, UUID
from datetime import datetime

from typing import Union


class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), primary_key=True, unique=True)
    password: Mapped[str] = mapped_column(String(50))


class Registry(Base):
    __tablename__ = "registry"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), ForeignKey(User.username))
    uuid: Mapped[UUID] = mapped_column(UUID(as_uuid=True))


class Note(Base):
    __tablename__ = "notes"

    uuid: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime())
    updated_at: Mapped[datetime] = mapped_column(DateTime())
    title: Mapped[str] = mapped_column(String(100))
    body: Mapped[str] = mapped_column(String(500))


def _create_user(db: Session, username: str, password: str) -> User:
    new_user = User(username=username, password=password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

def _get_all_notes(db: Session, user: User) -> Union[list[Note], None]:
    # uuids = db.query(Registry.uuid).filter(Registry.username == user.username).all()
    # print(f"//////////////////////////// {uuids} /////////////////////////")
    uuids = [uuid[0] for uuid in db.query(Registry.uuid).filter(Registry.username == user.username).all()]
    notes = [db.query(Note).filter(Note.uuid == uuid).first() for uuid in uuids]

    return notes

def _get_note(db: Session, note_id: UUID) -> Union[Note, None]:
    note = db.query(Note).filter(Note.uuid == note_id).first()
    return note

def _post_note(db: Session, user: User, note: Note) -> Note:
    new_note = Note(uuid=note.uuid,
                    created_at=note.created_at,
                    updated_at=note.updated_at,
                    title=note.title,
                    body=note.body)
    new_registry = Registry(username=user.username, uuid=note.uuid)
    db.add(new_note)
    db.add(new_registry)
    db.commit()
    db.refresh(new_note)
    db.refresh(new_registry)
    return new_note

def _update_note(db: Session, updated_note: Note) -> Union[Note, None]:
    note = db.query(Note).filter(Note.uuid == updated_note.uuid).first()
    if note:
        note.updated_at = updated_note.updated_at
        note.title = updated_note.title if updated_note.title is not None else note.title
        note.body = updated_note.body if updated_note.body is not None else note.body
        db.commit()
        db.refresh(note)
    return note

def _delete_note(db: Session, note_id: UUID) -> bool:
    note = db.query(Note).filter(Note.uuid == note_id).first()
    registry_note = db.query(Registry).filter(Registry.uuid == note_id).first()
    if note:
        db.delete(note)
        db.delete(registry_note)
        db.commit()
        return True
    return False

