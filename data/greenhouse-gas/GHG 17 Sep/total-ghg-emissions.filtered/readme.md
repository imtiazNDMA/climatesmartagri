# Greenhouse gas emissions - Data package

This data package contains the data that powers the chart ["Greenhouse gas emissions"](https://ourworldindata.org/grapher/total-ghg-emissions?tab=line&country=~PAK&v=1&csvType=filtered&useColumnShortNames=false) on the Our World in Data website. It was downloaded on September 18, 2026.

### Active Filters

A filtered subset of the full data was downloaded. The following filters were applied:
- country: , PAK
- tab: line

## CSV structure

Each row is an observation for an entity (usually a country or region) at a timepoint.

- "Entity" — the name of the entity, e.g. "United States".
- "Code" — our internal entity code. For most countries this is the [ISO alpha-3](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-3) code, e.g. "USA"; historical and other non-standard entities get a custom code.
- "Year" or "Day" — the timepoint. Annual data has a "Year" column holding an integer year; otherwise a "Day" column holds a date string in the form "YYYY-MM-DD".
- The final column is the data column — the time series that powers the chart. Downloaded with the "full data" option it corresponds to the time series below; with "only selected data visible in the chart" it is transformed depending on the chart type, so the correspondence may be less direct.


## Metadata.json structure

The .metadata.json file contains metadata about the data package. The "charts" key contains information to recreate the chart, like the title, subtitle etc. The "columns" key contains information about each of the columns in the csv, like the unit, timespan covered, citation for the data etc.

## How we process data at Our World in Data

Our World in Data is almost never the original producer of the data - almost all of the data we use has been compiled by others. If you want to re-use data, it is your responsibility to ensure that you adhere to the sources' license and to credit them correctly. Please note that a single time series may have more than one source - e.g. when we stitch together data from different time periods by different producers or when we calculate per capita metrics using population data from a second source.

Preparing this data involves several processing steps. Depending on the data, this can include standardizing country names and world region definitions, converting units, calculating derived indicators such as per capita measures, as well as adding or adapting metadata such as the name or the description given to an indicator.
[Read about our data pipeline](https://docs.owid.io/projects/etl/).

## Detailed information about the data


### Annual greenhouse gas emissions including land use
Greenhouse gas emissions are measured in tonnes of carbon dioxide-equivalents over a 100-year timescale.
Last updated: December 4, 2025  
Next expected update: December 2026  
Date range: 1850–2024  
Unit: tonnes of CO₂ equivalents  
Source: Jones et al. (2025) – with major processing by Our World in Data  

#### How to cite this data

Jones et al. (2025) – with major processing by Our World in Data

#### Notes on our processing step for this indicator
Emissions given in tonnes have been converted to carbon-dioxide equivalents over a 100-year timescale using a conversion factor of 273 for nitrous oxide, 29.8 for methane from fossil sources, and 27.2 for methane from agricultural and land use sources. These factors are taken from the 6th Assessment Report (AR6) of the Intergovernmental Panel on Climate Change (IPCC).


## Sources

These are the sources behind the data in this package. Each time series above names the ones it draws on in its citation.

### Jones et al. – National contributions to climate change

A dataset describing the global warming response to national emissions CO2, CH4 and N2O from fossil and land use sources during 1851-2024.

National CO2 emissions data are collated from the Global Carbon Project (Andrew and Peters, 2025; Friedlingstein et al., 2025). 

National CH4 and N2O emissions data are collated from PRIMAP-hist (HISTTP) (Gütschow et al., 2024).

We construct a time series of cumulative CO2-equivalent emissions for each country, gas, and emissions source (fossil or land use). Emissions of CH4 and N2O emissions are related to cumulative CO2-equivalent emissions using the Global Warming Potential (GWP*) approach, with best-estimates of the coefficients taken from the IPCC AR6 (Forster et al., 2021).

Warming in response to cumulative CO2-equivalent emissions is estimated using the transient climate response to cumulative carbon emissions (TCRE) approach, with best-estimate value of TCRE taken from the IPCC AR6 (Forster et al., 2021, Canadell et al., 2021). 'Warming' is specifically the change in global mean surface temperature (GMST).

The data files provide emissions, cumulative emissions and the GMST response by country, gas (CO2, CH4, N2O or 3-GHG total) and source (fossil emissions, land use emissions or the total).

Producer: Jones et al.  
Published: 2025-11-13  
Retrieved on: 2025-12-04  
Retrieved from: https://zenodo.org/records/7636699/latest  
Direct download: https://zenodo.org/records/16640595/files/EMISSIONS_ANNUAL_1830-2024.csv  
License: CC BY 4.0 (https://zenodo.org/records/7636699/latest)  

Citation: Jones, Matthew W., Glen P. Peters, Thomas Gasser, Robbie M. Andrew, Clemens Schwingshackl, Johannes Gütschow, Richard A. Houghton, Pierre Friedlingstein, Julia Pongratz, and Corinne Le Quéré. “National Contributions to Climate Change Due to Historical Emissions of Carbon Dioxide, Methane and Nitrous Oxide”. Scientific Data. Zenodo, November 13, 2025. https://doi.org/10.5281/zenodo.16640595.

    