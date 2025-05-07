from fastapi import FastAPI, Body, Path, status, UploadFile, File, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Annotated
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from uuid import UUID, uuid4
import csv, io, os
from enum import Enum
import uvicorn
from jose import jwt
from passlib.context import CryptContext

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db import (
    Base,
    _create_user,
    _get_user,
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


# Format: postgresql://username:password@host:port/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/demo_db")
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = session()
app = FastAPI()
oauth2scheme = OAuth2PasswordBearer(tokenUrl="token")
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

async def get_current_user(token: Annotated[str, Depends(oauth2scheme)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
    except:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    
    user = _get_user(
        db=db,
        username=username
    )
    if user: return user
    raise HTTPException(status_code=401, detail="Could not validate credentials")

def verify_password(password: str, hashed_password: str):
    return pwd_context.verify(secret=password, hash=hashed_password)

def get_hashed_password(password: str):
    return pwd_context.hash(password)
    
def authenticate_user(username: str, password: str):
    user = _get_user(db=db, username=username)

    if not user: return False
    if not verify_password(password=password, hashed_password=user.password):
        return False
    return user

@app.post("/token", include_in_schema=False)
async def login_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    
    access_token = jwt.encode(
        {"sub": user.username,
         "exp": datetime.now() + timedelta(minutes=15)},
         SECRET_KEY,
         algorithm=ALGORITHM
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/", include_in_schema=False)
async def redirect_to_docs():
    return RedirectResponse(url="/docs")

@app.post("/register/", response_model=UserOut, tags=[Tags.user])
async def register(user_info: Annotated[UserIn, Body()]):
    """
    Register as a user.
    - user(str): username
    - password(str): password
    """
    hashed_password = get_hashed_password(user_info.password)
    user = _create_user(db, user_info.username, hashed_password)
    return {"username": user.username, "status": "created new user!"}

@app.post("/upload_csv", status_code=201, tags=[Tags.notes])
async def upload_csv(csv_file: Annotated[UploadFile,
                    File(description="CSV file to be extracted for notes.",
                         media_type=".csv")],
                    user: Annotated[UserBase, Depends(get_current_user)]
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
async def get_all_notes(user: Annotated[UserBase, Depends(get_current_user)]) -> list[Note]:
    """
    Returns all the notes.
    """
    notes = _get_all_notes(
        db=db,
        user=user
    )
    return notes

@app.get("/notes/{note_id}", response_model=Note, tags=[Tags.notes])
async def get_note(note_id: Annotated[UUID, Path()],
                   user: Annotated[UserBase, Depends(get_current_user)]) -> Note:
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
async def post_note(note_data: Annotated[EditableNote, Body()],
                    user: Annotated[UserBase, Depends(get_current_user)]) -> Note:
    """
    Uploading a new note.
    - note_data(EditableNote): information of the new note.
    """
    note = _post_note(
        db,
        user = user,
        note = Note(
            uuid = uuid4(),
            created_at = datetime.now(),
            updated_at = datetime.now(),
            title = note_data.title or "",
            body = note_data.body or ""
        )
    )
    return note

@app.put("/notes/{note_id}", response_model=Note, tags=[Tags.notes])
async def update_note(note_id: Annotated[UUID, Path()],
                      updated_note_data: Annotated[EditableNote, Body()],
                      user: Annotated[UserBase, Depends(get_current_user)]) -> Note:
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
async def patch_note(note_id: Annotated[UUID, Path()],
                     new_data: Annotated[NoteBase, Body()],
                     user: Annotated[UserBase, Depends(get_current_user)]):
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
async def delete_note(note_id: Annotated[UUID, Path()],
                      user: Annotated[UserBase, Depends(get_current_user)]):
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