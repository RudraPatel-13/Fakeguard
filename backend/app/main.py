from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from analyzer import analyze_text

app = FastAPI(
    title="FakeGuard API",
    description="Rule-Based News Credibility Analyzer",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ArticleRequest(BaseModel):
    text: str


@app.get("/")
def root():
    return {
        "message": "FakeGuard API is running",
        "status": "success"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.post("/analyze")
def analyze_article(article: ArticleRequest):

    result = analyze_text(article.text)

    return {
        "message": "Article analyzed successfully",
        "text_length": len(article.text),
        "score": result["score"],
        "classification": result["classification"],
        "indicators": result["indicators"],
        "word_count": result["word_count"],
    }