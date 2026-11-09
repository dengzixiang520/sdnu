FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
# 业务数据（竞赛库、商品、课表）是部署内容而非代码，必须在镜像里带上，
# 否则容器首次启动时竞赛库与兑换商城都是空的。
COPY data ./data
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "zhihui_qilu.main:app", "--host", "0.0.0.0", "--port", "8000"]
