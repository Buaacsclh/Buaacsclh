import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.routes import router
from config import settings

app = FastAPI(
    title="智能眼镜人脸识别系统 - 边缘服务器",
    description="基于端边协同架构的人脸识别 API",
    version="1.0.0",
)

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """统一参数校验错误响应。"""
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "name": "",
            "confidence": 0.0,
            "detail": str(exc),
        },
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
