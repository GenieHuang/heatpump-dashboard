import pandas as pd
df = pd.read_csv('./data-raw/uscities.csv')

def data_process(uscities: pd.DataFrame) -> pd.DataFrame:
    uscities['city_state'] = uscities['city'] + ',' + uscities['state_name']
    return uscities[['city_state','lat','lng']]

df = data_process(df)

df.to_csv('./data/'+ 'cities.csv' , index=False)