# imports
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry

# import lets_plot as lp
import numpy as np
from shiny import App, Inputs, Outputs, Session, reactive, render, req, ui

# Requesting histrical weather API
def historical_weather():
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": 52.52,               # input
        "longitude": 13.41,              # input
        "start_date": "2024-02-14",      # input
        "end_date": "2024-02-28",        # input
        "daily": "temperature_2m_min",   # fixed
        "temperature_unit": "fahrenheit" # input
    }

    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]
    print(f"Coordinates {response.Latitude()}°N {response.Longitude()}°E")
    print(f"Elevation {response.Elevation()} m asl")
    print(f"Timezone {response.Timezone()} {response.TimezoneAbbreviation()}")
    print(f"Timezone difference to GMT+0 {response.UtcOffsetSeconds()} s")

    # Process daily data. The order of variables needs to be the same as requested.
    daily = response.Daily()
    daily_temperature_2m_min = daily.Variables(0).ValuesAsNumpy()

    daily_data = {"date": pd.date_range(
        start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
        end = pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
        freq = pd.Timedelta(seconds = daily.Interval()),
        inclusive = "left"
    )}
    daily_data["temperature_2m_min"] = daily_temperature_2m_min

    daily_dataframe = pd.DataFrame(data = daily_data)
    return daily_dataframe

# # lets-plot setup
# lp.LetsPlot.setup_html()

# create full and tidy data
cities = pd.read_csv("data/cities.csv")
daily_dataframe = historical_weather()
temp = daily_dataframe[['temperature_2m_min']].round().astype(int)
# Convert city_state column to list
city_list = cities['city_state'].values.tolist()

# # # calculate consistent limits for differential axis labels
# # diff_abs_max = np.max(np.abs([nfl["differential"].min(), nfl["differential"].max()]))
# # diff_min = -diff_abs_max
# # diff_max = diff_abs_max

# setup ui
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_select("city", "City", city_list, selected="New York,New York"),
        ui.input_date_range("dates", "Dates", start="2020-01-01"),
        ui.input_numeric("forcast_year", "Years to Forecast", 1, min=1, max=5),
        ui.input_radio_buttons(  "forecast_trend",  "Forecast Trend",  {"1": "Flat", "2": "Linear"}, selected="1"),  
        ui.input_radio_buttons(  "units",  "Units",  {"1": "Fahrenheit", "2": "Celsius"}, selected="1"),  
        ui.input_slider("temp","Plot Temperature",min = -15, max = 50, step = 1, value = 5),
        ui.input_checkbox_group("plot_options","Plot Options",choices=["Weekly Rolling Average","Monthly Rolling Average"],inline=False),
        ui.input_slider("temp","Table Temperature",min = -25, max = 60, step = 1, value =[0,15]),
    ),
    # ui.card(
    #     ui.output_ui("plot"),
    # ),
    ui.card(
        ui.output_data_frame("temp_table"),
    ),
    title = "Daily Heat Pump Efficiency Counter",
)


# setup server
def server(input: Inputs, output: Outputs, session: Session):
    @reactive.Calc
    def filtered_df() -> pd.DataFrame:

        df = daily_dataframe
        return df

    @reactive.Calc
    def season_table() -> pd.DataFrame:

        df = filtered_df()

        return df
    
    @render.text
    def value():
        return f"{input.select()}"

    @render.ui
    def plot():
        p = (
            lp.ggplot(filtered_df(), lp.aes(x="week", y="differential", color="team"))
            + lp.geom_path(tooltips=lp.layer_tooltips().line("Team: @team").line("Record: @wins - @losses"))
            + lp.ggsize(width=1000, height=700)
            + lp.ylim(diff_min, diff_max)
            + lp.labs(x="Week", y="Win-Loss Differential")
        )
        phtml = lp._kbridge._generate_static_html_page(p.as_dict(), iframe=True)
        return ui.HTML(phtml)

    @render.data_frame
    def temp_table():
        return render.DataGrid(season_table())

# run app
app = App(app_ui, server)