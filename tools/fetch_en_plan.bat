@echo off
cd /d C:\MyProjects\AntigravityProjects\AI_and_LLM\LayoutKeep\_artifacts\heldout\sources
curl -sL --max-time 900 -o sbb_development_plan_12_en.pdf "https://www.sbb.gov.tr/wp-content/uploads/2025/03/Twelfth-Development-Plan_2024-2028.pdf"
echo en_plan exit=%ERRORLEVEL%
