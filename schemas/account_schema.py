from pydantic import BaseModel, EmailStr, Field
from typing import Annotated

class Account(BaseModel):
    email: Annotated[EmailStr, Field(...)]
    password: Annotated[str, Field(...)]