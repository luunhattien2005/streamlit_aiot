@echo off
set "VENV_NAME=.venv"

if defined VIRTUAL_ENV (
    echo [OK] Dang chay trong moi truong ao tai: %VIRTUAL_ENV%
    goto :confirm
)

:: Nếu chưa kích hoạt, kiểm tra xem có thư mục .venv cục bộ không
if exist "%VENV_NAME%\Scripts\activate.bat" (
    echo [INFO] Dang tu dong kich hoat moi truong ao %VENV_NAME%...
    call "%VENV_NAME%\Scripts\activate.bat"
    goto :confirm
) else (
    echo ======================================================
    echo [CANH BAO NGUY HIEM]
    echo Khong tim thay moi truong ao nao dang hoat dong!
    echo Neu chay tiep, ban se xoa nham thu vien o Python GLOBAL.
    echo Tien trinh da bi chan de bao ve may tinh cua ban.
    echo ======================================================
    pause
    exit /b
)

:confirm
echo.
echo ======================================================
echo BAN DANG CHUAN BI XOA SACH TOAN BO THU VIEN TRONG:
echo %VIRTUAL_ENV%
echo ======================================================
echo.

choice /M "Ban co chac chan muon tiep tuc xoa khong"
if errorlevel 2 (
    echo [HUY] Da huy thao tac xoa.
    pause
    exit /b
)

echo Dang quet va xoa thu vien...
pip freeze > to_remove.txt

:: Kiểm tra nếu file to_remove.txt rỗng thì không cần xóa
for %%I in (to_remove.txt) do if %%~zI lss 3 (
    echo Moi truong ao hien tai dang trong san, khong co gi de xoa.
    del to_remove.txt
    pause
    exit /b
)

:: Gỡ cài đặt
pip uninstall -r to_remove.txt -y
del to_remove.txt

echo.
echo ======================================================
echo [THANH CONG] Da don dep sach moi truong ao!
echo Bay gio ban co the chay setup_venv.bat de cap nhat lai.
echo ======================================================
pause