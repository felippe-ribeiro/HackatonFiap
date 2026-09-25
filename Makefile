.PHONY: install seed api dashboard telegram followup test docker-up docker-down fmt

install:
	python -m pip install -r requirements.txt

seed:
	python -m scripts.seed_db

api:
	uvicorn app.main:app --reload --port 8000

dashboard:
	streamlit run dashboard/Home.py

telegram:
	python -m app.channels.telegram

followup:
	python -c "from app.services.followup import executar_ciclo; print(executar_ciclo(dry_run=True))"

test:
	pytest -q

avaliar:
	python -m scripts.avaliar

pdf:
	python -m pip install -q markdown xhtml2pdf pypdf
	python -m scripts.gerar_pdf

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v
