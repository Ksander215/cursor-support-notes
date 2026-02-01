@echo off
REM Запуск сервисов MCP в WSL и затем Cursor
REM Дважды кликните этот файл ПЕРЕД работой с Cursor — тогда Internal Error не появятся.
REM Путь к проекту в WSL: /home/alex/fastapi-project

echo.
echo [MCP] Запуск PostgreSQL и Redis в WSL...
echo.

wsl -d Ubuntu -e bash -c "cd /home/alex/fastapi-project && bash scripts/ensure_mcp_services.sh"
if errorlevel 1 (
    echo.
    echo [MCP] Ошибка запуска сервисов. Проверьте WSL и Docker.
    pause
    exit /b 1
)

echo.
echo [MCP] Сервисы готовы. Запуск Cursor...
echo.

set CURSOR_EXE=
if exist "%LOCALAPPDATA%\Programs\cursor\Cursor.exe" set CURSOR_EXE=%LOCALAPPDATA%\Programs\cursor\Cursor.exe
if exist "%LOCALAPPDATA%\Cursor\app\Cursor.exe" set CURSOR_EXE=%LOCALAPPDATA%\Cursor\app\Cursor.exe
if exist "%USERPROFILE%\AppData\Local\Programs\cursor\Cursor.exe" set CURSOR_EXE=%USERPROFILE%\AppData\Local\Programs\cursor\Cursor.exe

if defined CURSOR_EXE (
    start "" "%CURSOR_EXE%" "\\wsl.localhost\Ubuntu\home\alex\fastapi-project"
) else (
    echo Cursor не найден в стандартных путях.
    echo Откройте Cursor вручную и откройте папку проекта.
    echo.
    start "" "cursor" "\\wsl.localhost\Ubuntu\home\alex\fastapi-project"
)

echo.
echo [MCP] Готово. Internal Error не должны появляться, пока сервисы запущены.
echo.
timeout /t 3 >nul
