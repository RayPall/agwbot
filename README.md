## iDoklad Blog – generátor e-mailu

Streamlit app, která každý měsíc vybere 4 nové články z blogu iDoklad a připraví text e-mailu.

### Lokální spuštění

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
