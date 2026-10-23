from pydantic import BaseModel, Field, model_validator


class Question(BaseModel):
    question: str
    options: list[str]
    correct: int
    explanation: str
    source_id: str

    @model_validator(mode="after")
    def validate_choices(self):
        if len(self.options) != 4 or not 0 <= self.correct < 4:
            raise ValueError("Each question requires four options and one valid correct index")
        return self


class Quiz(BaseModel):
    title: str
    questions: list[Question]

    @model_validator(mode="after")
    def validate_count(self):
        if len(self.questions) != 3:
            raise ValueError("Exactly three questions are required")
        return self


class StudyStep(BaseModel):
    title: str
    task: str
    minutes: int
    source_ids: list[str]


class Plan(BaseModel):
    goal: str
    steps: list[StudyStep]


class ChatInput(BaseModel):
    course: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=4000)


class TopicInput(BaseModel):
    course: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    topic: str = Field(min_length=2, max_length=500)


class PlanInput(TopicInput):
    minutes_per_day: int = Field(default=30, ge=10, le=180)


class GradeInput(BaseModel):
    answers: list[int] = Field(min_length=3, max_length=3)
