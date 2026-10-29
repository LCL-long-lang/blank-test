@echo off
chcp 65001 >nul
setlocal
rem 双击启动：打开两个窗口分别运行后端（8000）和前端（3000），前端就绪后打开浏览器
set "ROOT=%~dp0"

if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo [错误] 没有找到后端虚拟环境 backend\.venv，请先按 README 安装后端依赖。
  pause
  exit /b 1
)
if not exist "%ROOT%backend\.env" (
  echo [错误] 没有找到 backend\.env，请复制 .env.example 为 .env 并填写 DASHSCOPE_API_KEY。
  pause
  exit /b 1
)
if not exist "%ROOT%frontend\node_modules" (
  echo [错误] 没有找到 frontend\node_modules，请先在 frontend 目录运行 npm install。
  pause
  exit /b 1
)

rem 端口已被占用时说明服务已经在运行，不再重复启动
netstat -ano | findstr /C:":8000 " | findstr LISTENING >nul
if errorlevel 1 (
  start "后端 - 端口 8000（关闭此窗口即停止）" /D "%ROOT%backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
) else (
  echo 后端已在运行（端口 8000）
)

netstat -ano | findstr /C:":3000 " | findstr LISTENING >nul
if errorlevel 1 (
  start "前端 - 端口 3000（关闭此窗口即停止）" /D "%ROOT%frontend" cmd /k "npm run dev"
) else (
  echo 前端已在运行（端口 3000）
)

echo 正在等待前端启动...
set /a n=0
:wait
curl.exe -s -o nul --noproxy "*" http://localhost:3000/ && goto open
set /a n+=1
if %n% geq 30 goto open
timeout /t 1 /nobreak >nul
goto wait

:open
start "" http://localhost:3000
echo 已打开 http://localhost:3000 ，关闭“后端”和“前端”两个窗口即可停止项目。
timeout /t 3 >nul
