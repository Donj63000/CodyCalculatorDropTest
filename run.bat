@echo off
rem -----------------------------------------------------------
rem  Lance DofusDropCalculator depuis ce dossier (target)
rem -----------------------------------------------------------

:: Se place dans le répertoire où se trouve le script
pushd "%~dp0"

:: Optionnel : si JAVA_HOME est défini, on l’utilise
if exist "%JAVA_HOME%\bin\java.exe" (
    set "JAVA_CMD=%JAVA_HOME%\bin\java.exe"
) else (
    set "JAVA_CMD=java"
)

:: Exécution – on garde la console ouverte après coup
"%JAVA_CMD%" --enable-native-access=ALL-UNNAMED ^
             -jar "%~dp0dofus-drop-calculator.jar"

pause
