# 使用轻量级的 Python 基础镜像
FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 生成 .pyc 文件，并使输出直接打印到控制台
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 安装系统依赖（如处理时区）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露目录以便挂载配置文件和状态文件
# 建议通过 docker-compose 挂载 config.yaml 和 state.json

# 运行程序
CMD ["python", "main.py"]
