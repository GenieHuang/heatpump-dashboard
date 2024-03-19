# imports
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry

# import lets_plot as lp
import numpy as np
from shiny import App, Inputs, Outputs, Session, reactive, render, req, ui
from shinywidgets import render_widget, output_widget

from ipyleaflet import Map,Marker

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
temp_F = daily_dataframe[['temperature_2m_min']].astype(float)
temp_C = (temp_F - 32)/1.8
# Convert city_state column to list
city_list = cities['city_state'].tolist()

# # # calculate consistent limits for differential axis labels
# # diff_abs_max = np.max(np.abs([nfl["differential"].min(), nfl["differential"].max()]))
# # diff_min = -diff_abs_max
# # diff_max = diff_abs_max

# setup ui
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_selectize("city", "City", city_list, selected="Urbana,Illinois"),
        ui.output_text("selected_lat_lng"),
        ui.input_date_range("dates", "Dates", start="2022-01-01", end="2024-01-01",max="2024-01-01",min="2020-01-01"),
        ui.input_numeric("forecast_year", "Years to Forecast", 1, min=1, max=5),
        ui.input_radio_buttons( "forecast_trend",  "Forecast Trend",  {"1": "Flat", "2": "Linear"}, selected="1"),  
        ui.input_radio_buttons( "units",  "Units",  {"1": "Fahrenheit", "2": "Celsius"}, selected="1"),  
        ui.output_ui("plot_temp_slider"),
        ui.input_checkbox_group("plot_options","Plot Options",choices=["Weekly Rolling Average","Monthly Rolling Average"],inline=False),
        ui.output_ui("table_temp_slider"),
        ui.hr(),
        output_widget("map",height="300px"),
        width=300,
        open='always'
    ),
    ui.page_navbar(
        ui.nav_panel("Historical",
                     ui.output_ui("historical_plot"),
                     ui.hr(),
                     ui.output_data_frame("historical_df")),
        ui.nav_panel("Forecast",
                     ui.output_ui("forecast_plot"),
                     ui.hr(),
                     ui.output_data_frame("forecast_df")),
        ui.nav_panel("About"),
    ),
    title = "Daily Heat Pump Efficiency Counter",
)


# setup server
def server(input: Inputs, output: Outputs, session: Session):
    def current_lat_lng():
        selected_city = input.city()
        # Get the row of the selected city
        selected_lat_lng= cities[cities["city_state"] == selected_city].iloc[0]
        lat = selected_lat_lng["lat"]
        lng = selected_lat_lng["lng"]
        return lat,lng
    
    @output
    @render.text("selected_lat_lng")
    def selected_lat_lng():
        lat,lng = current_lat_lng()
        return f"{lat:.4f}°N, {lng:.4f}°E"
    
    @render_widget("map")
    def map():
        lat,lng = current_lat_lng()
        map = Map(center = (lat,lng), zoom = 12)
        marker = Marker(location=(lat, lng))
        map.add_layer(marker)
        return map
    
    @render.data_frame("historical_df") 
    def historical_df():
        return render.DataGrid(calculate_table(),summary=False,height='3000px',width=1600)
    
    @reactive.Calc
    def calculate_table():
        units = input.units()
        selected_temp = input.table_temp()
        temp_list = list(range(selected_temp[0], selected_temp[1] + 1))
        historical_rows = []
        if units == "1":  # Fahrenheit

            for temp in temp_list:
                days_below = temp_F[temp_F["temperature_2m_min"] < temp].shape[0]
                proportion_below = round(days_below / temp_F.shape[0],3)
                historical_rows.append({
                    "Temp": temp,
                    "Days Below": days_below,
                    "Proportion Below": proportion_below
                })
            
        else:  # Celsius

            for temp in temp_list:
                days_below = temp_C[temp_C["temperature_2m_min"] < temp].shape[0]
                proportion_below = round(days_below / temp_C.shape[0],3)
                historical_rows.append({
                    "Temp": temp,
                    "Days Below": days_below,
                    "Proportion Below": proportion_below
                })

        historical_df = pd.DataFrame(historical_rows)
        return historical_df
    
    @output
    @render.ui("plot_temp_slider")
    def plot_temp_slider():
        units = input.units()
        if units == "1":  # Fahrenheit
            return ui.input_slider("plot_temp", "Plot Temperature", min=-15, max=50, step=1, value=5)
        else:  # Celsius
            return ui.input_slider("plot_temp", "Plot Temperature", min=-25, max=10, step=1, value=-15)
    
    @output
    @render.ui("table_temp_slider")
    def table_temp_slider():
        units = input.units()
        if units == "1":  # Fahrenheit
            return ui.input_slider("table_temp", "Table Temperature", min=-25, max=60, step=1, value=[0,15])
        else:  # Celsius
            return ui.input_slider("table_temp", "Table Temperature", min=-30, max=15, step=1, value=[-20,-10])

    

# run app
app = App(app_ui, server)