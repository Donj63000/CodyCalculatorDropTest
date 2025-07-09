@echo off
set FX=%~dp0javafx
java --module-path "%FX%" --add-modules javafx.controls,javafx.media -jar "%~dp0dofus-drop-calculator.jar"
pause
