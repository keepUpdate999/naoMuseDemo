from typing import Literal
from pydantic import BaseModel, Field, TypeAdapter


class Task(BaseModel):
    id: int = Field(ge=1, le=12)
    title: str = Field(max_length=100)
    owner: str = Field(max_length=100)
    status: Literal['待处理', '进行中', '已完成']
    date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')


class Note(BaseModel):
    id: str = Field(max_length=80)
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(max_length=20000)


class Form(BaseModel):
    name: str = Field(max_length=100)
    session: Literal['上午场', '下午场']
    people: int = Field(ge=1, le=20)
    remark: str = Field(max_length=2000)


def validate_data(key, value):
    if key == 'tasks':
        items = TypeAdapter(list[Task]).validate_python(value)
        if len(items) != 12 or {x.id for x in items} != set(range(1, 13)):
            raise ValueError('Invalid task IDs')
        return [x.model_dump() for x in items]
    if key == 'notes':
        items = TypeAdapter(list[Note]).validate_python(value)
        if len(items) > 100 or len({x.id for x in items}) != len(items):
            raise ValueError('Invalid notes')
        return [x.model_dump() for x in items]
    if key == 'form':
        return Form.model_validate(value).model_dump()
    raise ValueError('Read-only dataset')
