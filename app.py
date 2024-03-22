# imports
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import numpy as np
from shiny import App, Inputs, Outputs, Session, reactive, render, req, ui
from shinywidgets import render_widget, output_widget

from ipyleaflet import Map,Marker
from ipywidgets import Layout

from prophet import Prophet

# Requesting histrical weather API
def historical_weather(lat, lng, start_date, end_date, units):
    # Setup the Open-Meteo API client with cache and retry on error
    cache_session = requests_cache.CachedSession('.cache', expire_after = -1)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Request url and params
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,               # input
        "longitude": lng,              # input
        "start_date": start_date,      # input
        "end_date": end_date,        # input
        "daily": "temperature_2m_min",   # fixed
        "temperature_unit": units # input
    }

    responses = openmeteo.weather_api(url, params=params)

    # Process first location. Add a for-loop for multiple locations or weather models
    response = responses[0]

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
    return daily_dataframe, response.Latitude(),response.Longitude()

# About page content
def about_content():
    context = """
# About This Dashboard

This dashboard is designed to support the decision-making process of the installation of heat pumps.
It leverages historical weather information and forecast information to provide a comprehensive analysis of weather patterns in your selected location.
Through interactive and well-formatted plots and tables, you are able to gain immediate insights into historical weather conditions and future predictions,
assisting in assessing the efficiency of installing a heat pump.

## Instructions:

1. Use the left sidebar to customize your selection, including location, date range, and measurement units.
2. Temperature Sliders:
    - **Plot Temperature Slider:** Set a temperature value to visually distinguish days below this temperature in the plot:
      days below are marked in grey and above in black, offering a clear view of cooler days.
    - **Table Temperature Slider:** Set a temperature range to show a summary for each temperature within this range,
      including the number of days below each temperature and proportion of the total.
3. Explore rolling average temperature plots by selecting your desired plot options.
4. On the forecast page, choose your trend prediction and specify the forecast year.

## References

1.**Location Data:** SimpleMaps. (2024). U.S. City and State Data (Version 1.78) [Data set]. Retrieved from https://simplemaps.com/static/data/us-cities/1.78/basic/simplemaps_uscities_basicv1.78.zip
2.**Weather Data:** Open-Meteo. (n.d.). Historical Weather API. Retrieved from https://open-meteo.com/en/docs/historical-weather-api
    """
    return context


# Create full and tidy data
cities = pd.read_csv("data/cities.csv")

# Convert city_state column to list
city_list = cities["city_state"].tolist()

# setup ui
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_selectize("city", "City", city_list, selected="Urbana,Illinois"),
        ui.output_text("selected_lat_lng"),
        ui.input_date_range("dates", "Dates", start="2022-01-01", end="2024-01-01",max="2024-01-01",min="2020-01-01"),
        ui.input_numeric("forecast_year", "Years to Forecast", 1, min=1, max=5),
        ui.input_radio_buttons( "forecast_trend",  "Forecast Trend",  {"flat": "Flat", "linear": "Linear"}, selected="flat"),  
        ui.input_radio_buttons( "units",  "Units",  {"fahrenheit": "Fahrenheit", "celsius": "Celsius"}, selected="fahrenheit"),  
        ui.output_ui("plot_temp_slider"),
        ui.input_checkbox_group("plot_options","Plot Options",choices=["Weekly Rolling Average","Monthly Rolling Average"],inline=False),
        ui.output_ui("table_temp_slider"),
        ui.hr(),
        output_widget("map"),
        width=350,
        open="always"
    ),
    ui.page_navbar(
        ui.nav_panel("Historical",
                     ui.output_plot("historical_plot"),
                     ui.hr(),
                     ui.output_data_frame("historical_df")),
        ui.nav_panel("Forecast",
                     ui.output_plot("forecast_plot"),
                     ui.hr(),
                     ui.output_data_frame("forecast_df")),
        ui.nav_panel("About",
                     ui.markdown(about_content())),
    ),
    title = "Daily Heat Pump Efficiency Counter",
)


# setup server
def server(input: Inputs, output: Outputs, session: Session):
    def get_data():

        global start_date, end_date

        # Params
        lat, lng = current_lat_lng()
        start_date = input.dates()[0]
        end_date = input.dates()[1]
        units = input.units()

        # Getting historical weather data
        daily_dataframe, lat, lng = historical_weather(lat, lng,start_date, end_date, units)

        return daily_dataframe, lat, lng

    def current_lat_lng():
        selected_city = input.city()
        # Get the lat and lng of the selected city_state
        selected_lat_lng= cities[cities["city_state"] == selected_city].iloc[0]
        lat = selected_lat_lng["lat"]
        lng = selected_lat_lng["lng"]
        return lat,lng
    
    # Coordinates
    @output
    @render.text("selected_lat_lng")
    def selected_lat_lng():
        _, lat, lng = get_data()
        return f"{lat:.4f}°N, {lng:.4f}°E"
    
    # Map
    @render_widget("map")
    def map():
        _, lat, lng = get_data()
        map = Map(center = (lat,lng), zoom = 12, layout=Layout(height="200px"))
        marker = Marker(location=(lat, lng))
        map.add_layer(marker)
        return map
    
    # Historical table
    @render.data_frame("historical_df") 
    def historical_df():
        return render.DataGrid(calculate_historical_table(),summary=False,height="3000px",width=1600)
    
    # Calculate the historical table
    @reactive.Calc
    def calculate_historical_table():
        selected_temp = input.table_temp()
        temp_list = list(range(selected_temp[1], selected_temp[0] - 1, -1))
        historical_rows = []
        daily_dataframe,_,_ = get_data()
        temp_table = daily_dataframe[["temperature_2m_min"]].astype(float)
        
        for temp in temp_list:
                days_below = temp_table[temp_table["temperature_2m_min"] < temp].shape[0]
                proportion_below = round(days_below / temp_table.shape[0],3)
                historical_rows.append({
                    "Temp": temp,
                    "Days Below": days_below,
                    "Proportion Below": proportion_below
                })

        historical_df = pd.DataFrame(historical_rows)
        return historical_df
    
    # Plot slider
    @output
    @render.ui("plot_temp_slider")
    def plot_temp_slider():
        units = input.units()
        if units == "fahrenheit":
            return ui.input_slider("plot_temp", "Plot Temperature", min=-15, max=50, step=1, value=5)
        else:  # Celsius
            return ui.input_slider("plot_temp", "Plot Temperature", min=-25, max=10, step=1, value=-15)
    
    # Table slider
    @output
    @render.ui("table_temp_slider")
    def table_temp_slider():
        units = input.units()
        if units == "fahrenheit":
            return ui.input_slider("table_temp", "Table Temperature", min=-25, max=60, step=1, value=[0,15])
        else:  # Celsius
            return ui.input_slider("table_temp", "Table Temperature", min=-30, max=15, step=1, value=[-20,-10])

    # Historical plot
    @output
    @render.plot(alt="historical_plot")
    # @render.ui("historical_plot")
    def historical_plot():

        daily_dataframe,_,_ = get_data()
        daily_dataframe["date"] = pd.to_datetime(daily_dataframe["date"])

        daily_dataframe["weekly_rolling"] = daily_dataframe["temperature_2m_min"].rolling(window=7).mean()
        daily_dataframe["monthly_rolling"] = daily_dataframe["temperature_2m_min"].rolling(window=30).mean()

        selected_temp_line = input.plot_temp()
        plot_options = input.plot_options()
        
        fig, ax = plt.subplots(figsize=(14, 5))

        ax.scatter(daily_dataframe["date"], daily_dataframe["temperature_2m_min"], color="grey", alpha=0.4, s=10)

        ax.scatter(daily_dataframe[daily_dataframe["temperature_2m_min"] > selected_temp_line]["date"], 
               daily_dataframe[daily_dataframe["temperature_2m_min"] > selected_temp_line]["temperature_2m_min"], 
               color="black", s=10)
        
        # Horizontal line for the selected temperature
        ax.axhline(y=selected_temp_line, color="grey", linewidth=0.5)

        # Weekly and monthly rolling averages
        if "Weekly Rolling Average" in plot_options:
            ax.plot(daily_dataframe["date"], daily_dataframe["weekly_rolling"], color="darkorange", linewidth=2)

        if "Monthly Rolling Average" in plot_options:
            ax.plot(daily_dataframe["date"], daily_dataframe["monthly_rolling"], color="cornflowerblue", linewidth=2)

        # Formatting the axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

        ax.set_ylabel("Daily Minimum Temperature °F")

        plt.xticks(rotation=0)
        plt.grid(True,alpha = 0.5)
        plt.tight_layout()

        return fig

    def get_forecast_df_fig():
        daily_dataframe,_,_ = get_data()
        daily_dataframe.rename(columns={"date":"ds","temperature_2m_min":"y"},inplace = True)
        daily_dataframe["ds"] = daily_dataframe["ds"].dt.tz_localize(None)

        forecast_trend = input.forecast_trend()
        forecast_year = input.forecast_year()

        # Forecast
        m = Prophet(growth = forecast_trend,interval_width=0.95)
        m.fit(daily_dataframe)

        future = m.make_future_dataframe(periods=(365*int(forecast_year)),include_history=False)

        forecast = m.predict(future)
        future_dataframe = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]]

        fig = m.plot(forecast)

        return future_dataframe, fig
    
    # Calculate the forecast table
    @reactive.Calc
    def calculate_forecast_table():

        future_dataframe,_ = get_forecast_df_fig()

        temp_table = future_dataframe[["yhat_lower"]].astype(float)

        selected_temp = input.table_temp()
        temp_list = list(range(selected_temp[1], selected_temp[0] - 1, -1))
        forecast_rows = []

        for temp in temp_list:
                days_below = temp_table[temp_table["yhat_lower"] < temp].shape[0]
                proportion_below = round(days_below / temp_table.shape[0],3)
                forecast_rows.append({
                    "Temp": temp,
                    "Days Below": days_below,
                    "Proportion Below": proportion_below
                })

        forecast_df = pd.DataFrame(forecast_rows)
        return forecast_df
    
    # Forecast table
    @render.data_frame("forecast_df") 
    def forecast_df():

        # No forecast if there is less than one year of training data
        if (end_date - start_date).days < 365:
            pass
        else:
            return render.DataGrid(calculate_forecast_table(),summary=False,height="3000px",width=1600)

    # Forecast plot
    @output
    @render.plot(alt="forecast_plot")
    def forecast_plot():

        # No forecast if there is less than one year of training data
        if (end_date - start_date).days < 365:
            pass
        else:
            _, fig = get_forecast_df_fig()
            ax = fig.gca()

            selected_temp_line = input.plot_temp()

            daily_dataframe,_,_ = get_data()
            daily_dataframe["date"] = pd.to_datetime(daily_dataframe["date"])

            ax.scatter(daily_dataframe["date"], daily_dataframe["temperature_2m_min"], color="black", s=10)

            # Horizontal line for the selected temperature
            ax.axhline(y=selected_temp_line, color="grey", linewidth=0.5)

            plt.ylabel("Daily Minimum Temperature °F")
            plt.xlabel("")
            
            return fig

# run app
app = App(app_ui, server)