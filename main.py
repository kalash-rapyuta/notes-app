from fastapi import FastAPI, Body, Path, status, UploadFile, File, HTTPException
from typing import Annotated
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID, uuid4
import csv, io, os
from enum import Enum
import uvicorn

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db import (
    Base,
    _create_user,
    _post_note,
    _get_all_notes,
    _get_note,
    _update_note,
    _delete_note
)


class UserBase(BaseModel):
    username: Annotated[str, Body()]

class UserIn(UserBase):
    password: Annotated[str, Body()]

class UserOut(UserBase):
    status: Annotated[str, Body()]

class NoteBase(BaseModel):
    title: Annotated[str, Body(default=None, max_length=100)] 
    body: Annotated[str, Body(default=None, max_length=500)]

class Note(NoteBase):
    uuid: Annotated[UUID, Body()] = Field(default_factory=uuid4)
    created_at: Annotated[datetime, Body()] = Field(default_factory=datetime.now())
    updated_at: Annotated[datetime, Body()] = Field(default_factory=datetime.now())

class EditableNote(NoteBase):
    pass

class Tags(Enum):
    user = "user"
    notes = "notes"


USER = UserBase(username="kalash")
# PASS = "autobootstrap"

# Format: postgresql://username:password@host:port/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/demo_db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL, echo=False)
session = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)
db = session()

NOTES: list[Note] = list()
app = FastAPI()
# oauth2scheme = OAuth2PasswordBearer(tokenUrl="autobootstrap")


# @app.post("/login/", response_model=UserOut, tags=[Tags.user])
# async def login(user_info: Annotated[UserIn, Body()], token: Annotated[str, Depends(oauth2scheme)]):
#     """
#     Login as a user.
#     - user(str): username
#     - password(str): password
#     """
#     if user_info.user == USER and user_info.password == PASS:
#         return {**user_info.model_dump(), "status": "Logged In Successfully!"}
#     return {**user_info.model_dump(), "status": "Wrong credentials!"}

@app.post("/register/", response_model=UserOut, tags=[Tags.user])
async def register(user_info: Annotated[UserIn, Body()]):
    """
    Register as a user.
    - user(str): username
    - password(str): password
    """
    user = _create_user(db, user_info.username, user_info.password)
    return {"username": user.username, "status": "created new user!"}

@app.post("/upload_csv", status_code=201, tags=[Tags.notes])
async def upload_csv(csv_file: Annotated[UploadFile,
                    File(description="CSV file to be extracted for notes.",
                         media_type=".csv")]
                    ):
    """
    Uploading and extracting notes from a CSV file.
    - csv_file(File): csv file with at least title and body columns for every entry
    """
    file_data = await csv_file.read()
    decoded = file_data.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    total_rows = 0

    for row in reader:
        try:
            title = row.get("title")
            body = row.get("body")
            await post_note(EditableNote(title=title, body=body))
            total_rows += 1
        except:
            raise HTTPException(status_code=401, detail="CSV seems messed up!")

    return {"result": f"{total_rows} note{'s' if total_rows > 1 else ''} uploaded and created successfully!"}

@app.get("/notes/", response_model=list[Note], tags=[Tags.notes])
async def get_all_notes() -> list[Note]:
    """
    Returns all the notes.
    """
    notes = _get_all_notes(
        db=db,
        user=USER
    )
    return notes

@app.get("/notes/{note_id}", response_model=Note, tags=[Tags.notes])
async def get_note(note_id: Annotated[UUID, Path()]) -> Note:
    """
    Returns note by id.
    - note_id(UUID): unique id of the note
    """
    note = _get_note(
        db=db,
        note_id = note_id
    )
    if note: return note
    raise HTTPException(status_code=404, detail="Note not found!")

@app.post("/notes/", response_model=Note, status_code=status.HTTP_201_CREATED, tags=[Tags.notes])
async def post_note(note_data: Annotated[EditableNote, Body()]) -> Note:
    """
    Uploading a new note.
    - note_data(EditableNote): information of the new note.
    """
    note = _post_note(
        db,
        user = USER,
        note = Note(
            uuid = uuid4(),
            created_at = datetime.now(),
            updated_at = datetime.now(),
            title = note_data.title or "",
            body = note_data.body or ""
        )
    )
    NOTES.append(note)
    return note

@app.put("/notes/{note_id}", response_model=Note, tags=[Tags.notes])
async def update_note(note_id: Annotated[UUID, Path()], updated_note_data: Annotated[EditableNote, Body()]) -> Note:
    """
    Updating the whole note.
    - note_id(UUID): unique id of the note
    - updated_note_data: new data for the note
    """

    updated_note = _update_note(
        db=db,
        updated_note=Note(
                uuid = note_id,
                created_at = datetime.now(),
                updated_at = datetime.now(),
                title = updated_note_data.title,
                body = updated_note_data.body
        )
    )
    if updated_note: return updated_note
    raise HTTPException(status_code=404, detail="Note not found!")

@app.patch("/notes/{note_id}", response_model=Note, tags=[Tags.notes])
async def patch_note(note_id: Annotated[UUID, Path()], new_data: Annotated[NoteBase, Body()]):
    """
    Patching new information in a note.
    - note_id(UUID): unique id of the note
    - new_data: new data for the note
    """
    note = _get_note(
        db=db,
        note_id=note_id
    )
    note = Note(**(note.__dict__))
    updated_data = new_data.model_dump(exclude_unset=True)
    updated_note = note.model_copy(update=updated_data)
    updated_note = _update_note(
        db=db,
        updated_note=updated_note
    )
    if updated_note: return updated_note
        
    raise HTTPException(status_code=404, detail="Note not found!")

@app.delete("/notes/{note_id}", tags=[Tags.notes])
async def delete_note(note_id: Annotated[UUID, Path()]):
    """
    Deleting a note.
    - note_id(UUID): unique id of the note to be deleted.
    """
    result = _delete_note(
        db=db,
        note_id=note_id
    )
    if result: return {"result": "Deleted note successfully!"}
    raise HTTPException(status_code=404, detail="Note not found!")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)