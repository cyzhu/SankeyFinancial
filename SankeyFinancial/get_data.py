from utils import GetData

if __name__ == "__main__":
    cik = "320193"
    gd = GetData(
        your_company_name="Aetna",
        your_company_email="zhuc@aetna.com",
        cik=cik,
        company_ticker="aapl",
    )
    gd.prepare(2021)
    gd.show("png","./plots")
