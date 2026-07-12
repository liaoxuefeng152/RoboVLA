# RoboVLA V2.0 SpringBoot 后端 Docker 镜像
FROM eclipse-temurin:17-jdk-alpine

WORKDIR /app

# 安装调试工具
RUN apk add --no-cache curl tzdata && \
    cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# 复制构建产物
COPY target/robovla-backend-2.0.0.jar app.jar

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8080/actuator/health || exit 1

EXPOSE 8080

ENTRYPOINT ["java", \
  "-Xms512m", "-Xmx1024m", \
  "-XX:+UseG1GC", \
  "-XX:MaxGCPauseMillis=200", \
  "-Djava.security.egd=file:/dev/./urandom", \
  "-jar", "app.jar"]
