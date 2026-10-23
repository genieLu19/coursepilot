# Как загрузить проект в GitHub

## Через браузер

1. Распакуйте архив `coursepilot-github.zip`.
2. На GitHub создайте пустой репозиторий `coursepilot`. Не добавляйте автоматически README и лицензию: они уже есть в проекте.
3. В репозитории выберите **uploading an existing file** или **Add file → Upload files**.
4. Перетащите содержимое папки `coursepilot`, а не ZIP и не внешнюю папку целиком. В корне репозитория должны находиться `README.md`, `pyproject.toml`, папки `coursepilot`, `data`, `tests` и остальные файлы.
5. Проверьте наличие `.gitignore`, `.env.example` и `.github/workflows/tests.yml`. Некоторые файловые менеджеры скрывают файлы и папки с точкой. При необходимости включите их отображение или используйте Git-команды ниже.
6. Нажмите **Commit changes**.

Файл `.env.example` содержит только имена настроек. `.env.local` с настоящим ключом не должен попадать на GitHub.

## Через Git в PowerShell

Откройте PowerShell в распакованной папке `coursepilot`. Если Git не установлен, установите его с [git-scm.com](https://git-scm.com/downloads), затем заново откройте PowerShell.

```powershell
git init -b main
git add .
git status --short
```

Проверьте, что в списке нет `.env.local`, `.env`, `runtime` и `.venv`. Затем:

```powershell
git commit -m "Add CoursePilot AI learning assistant"
git remote add origin https://github.com/genieLu19/coursepilot.git
git push -u origin main
```

Сначала создайте пустой репозиторий с этим именем в своём аккаунте. При первом push может потребоваться вход в GitHub.

## Описание репозитория

**About:** AI learning assistant with hybrid RAG, source citations, quizzes and personalized study plans.

**Topics:** `llm`, `rag`, `ai-assistant`, `openai`, `fastapi`, `hybrid-search`, `education`, `python`.

В README уже описаны фактически реализованные возможности и границы проверки. Метрики новых моделей добавляйте после собственного запуска оценки.
