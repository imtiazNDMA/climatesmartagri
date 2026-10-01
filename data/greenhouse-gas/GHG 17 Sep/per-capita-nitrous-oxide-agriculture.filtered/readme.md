# Per capita nitrous oxide emissions from agriculture - Data package

This data package contains the data that powers the chart ["Per capita nitrous oxide emissions from agriculture"](https://ourworldindata.org/grapher/per-capita-nitrous-oxide-agriculture?tab=line&country=~PAK&v=1&csvType=filtered&useColumnShortNames=false) on the Our World in Data website. It was downloaded on September 18, 2026.

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


### Agriculture
Emissions are measured in kilograms of carbon dioxide-equivalents per person.
Last updated: February 10, 2026  
Next expected update: February 2027  
Date range: 1990–2023  
Unit: kilograms per person  
Source: Climate Watch (2026); Population based on various sources (2024) – with major processing by Our World in Data  

#### How to cite this data

Climate Watch (2026); Population based on various sources (2024) – with major processing by Our World in Data

#### How this data is described by its producers
Agriculture sector contains emissions from the following activities:
  - CH₄ emissions from Enteric fermentation (livestock).
  - CH₄ and N₂O emissions from Manure management (livestock).
  - CH₄ emissions from Rice cultivation.
  - N₂O emissions from Agriculture soils.
  - Crop residues.
  - Drained organic soils.
  - Manure applied to soils.
  - Manure left on pasture.
  - Synthetic fertilizers.
  - CH₄ and N₂O emissions from Other agricultural sources (burning of crop residues and savanna).

  Please note that emissions associated with agriculture related energy use are reported under Energy sector, and thus not included here.


## Sources

These are the sources behind the data in this package. Each time series above names the ones it draws on in its citation.

### Climate Watch – Greenhouse gas emissions by sector

Climate Watch Historical Emissions data contains sector-level greenhouse gas (GHG) emissions, including emissions of the six major GHGs from most major sources and sinks. Non-CO₂ emissions are expressed in CO₂ equivalents using 100-year global warming potential values from the Intergovernmental Panel on Climate Change (IPCC) Fifth Assessment Report (AR5).

More information about their data sources and methodology can be found in their [FAQ page](https://www.climatewatchdata.org/about/faq/ghg). Specifically, the definitions of all Climate Watch data sectors and their methodology are explained in [this document](https://files.wri.org/d8/s3fs-public/2024-05/climate-watch-country-greenhouse-gas-emissions-data-methodology.pdf?VersionId=1geU96keSmqZlUjv41FNGB4CLpHQbruN).

Producer: Climate Watch  
Published: 2026-01-15  
Retrieved on: 2026-02-10  
Retrieved from: https://www.climatewatchdata.org/data-explorer/historical-emissions  
License: CC BY 4.0 (https://www.climatewatchdata.org/about/permissions)  

Citation: Climate Watch. 2026. Washington, DC: World Resources Institute (WRI). Available online at: https://www.climatewatchdata.org

Climate Watch data are derived from several sources.
- Data on land-Use change and forestry, and agriculture, are sourced from the Food and Agriculture Organization of the United Nations, FAOSTAT Emissions Database.
- Data on greenhouse gas emissions from fuel combustion are sourced from the OECD/IEA.

### Various sources – Population

Our World in Data builds and maintains a long-run dataset on population by country, region, and for the world, based on various sources.

You can find more information on these sources and how our time series is constructed on this page: https://ourworldindata.org/population-sources

Producer: Various sources  
Published: 2024-07-15  
Retrieved on: 2026-03-31  
Retrieved from: https://ourworldindata.org/population-sources  
License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)  

Citation: The long-run data on population is based on various sources, described on this page: https://ourworldindata.org/population-sources

    