#!/bin/bash

sleep 15

# Di chuyển đến thư mục dự án Django
cd /home/aais/Documents/homestay || exit 1

# Đợi các dịch vụ khác khởi động nếu cần
echo "Đang chờ PostgreSQL..."
while ! pg_isready -h 127.0.0.1 -p 5432 -U postgres >/dev/null 2>&1; do
    echo "Chưa kết nối được PostgreSQL, đợi 10 giây..."
    sleep 10
done
echo "PostgreSQL đã sẵn sàng!"

# Lấy cấu hình từ app.yml
PORT_APP=$(grep 'PORT_APP' app.yaml | awk '{print $2}' | tr -d '[:space:]')
NUM_WORKERS=$(grep 'NUM_WORKERS' app.yaml | awk '{print $2}' | tr -d '[:space:]')

echo "PORT_APP is: $PORT_APP"
echo "NUM_WORKERS is: $NUM_WORKERS"

# Kill process đang chiếm port nếu có
PIDS=$(lsof -t -i :$PORT_APP)
if [ -n "$PIDS" ]; then
  echo "Found process(es) on port $PORT_APP: $PIDS"
  for pid in $PIDS; do
    echo "Killing PID $pid..."
    kill $pid
    sleep 1
    if kill -0 $pid 2>/dev/null; then
      echo "Process $pid vẫn chưa dừng, dùng SIGKILL..."
      kill -9 $pid
    else
      echo "Process $pid đã dừng."
    fi
  done
else
  echo "Không có process nào đang chiếm port $PORT_APP."
fi

# Thu gom static files (CSS, JS, images) vào static_root/
python manage.py collectstatic --noinput 2>/dev/null

# Chạy uvicorn
uvicorn config.asgi:application --host 0.0.0.0 --port $PORT_APP --workers $NUM_WORKERS --no-access-log
