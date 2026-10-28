# Climate Smart Agriculture Portal

A map-first portal that shows Pakistan's agriculture, climate, water, forecast and hazard information to disaster management stakeholders, and helps them read it.

## Language

### The portal

**Section**:
One topic of the portal (land classification, irrigation practices, hazards, ...) with its own layers, figures and charts.
_Avoid_: page, tab, module

**Layer**:
One thing that can be drawn on the map, belonging to a section.
_Avoid_: dataset, overlay

**Class view**:
A layer that draws one class of the annual land classification, such as Trees or Crops, from the same year's tiles as the full classification.
_Avoid_: forest layer, mask

**Place**:
The country, a province or a district that figures and charts are about. A section without figures at a place falls back to the nearest place above it.
_Avoid_: region, area, location

**View**:
What a reader has on screen: the open section, place, year, layers and forecast.
_Avoid_: state, screen

### Forecasts and hazards

**Forecast**:
A field predicted by a weather model run for a valid time, fetched from PMD.

**Hazard product**:
A named agricultural threat (frost, heat stress, heavy rain, strong wind, low visibility) read from a forecast with bands of severity.
_Avoid_: alert, hazard layer

**Derived model**:
A field the portal computes from forecasts, such as frost degree-hours, because no forecast gives it directly.

**Observation**:
One year of the annual land classification, measured for every place from the same product the same way.

**Classified land**:
The part of a place an observation assigns to a class. Cloud and no data are not classified, so a class's share of classified land and its share of all land differ; coverage says how much of the place was classified.
_Avoid_: total area, land cover (for the classified part)

**Net class-area change**:
The difference in one class's area between two observations. It says how much more or less land was classified as the class, not which land moved between classes or why.
_Avoid_: converted, conversion, transition, lost to, turned into

**Guidance**:
The portal's own reading of forecasts for agriculture. It is never an official warning.
_Avoid_: warning, alert

**District risk**:
Each district's low, medium or high band for one hazard product at one valid time.

**Crop stage**:
Where a crop is in its season at a place and date (sowing, growing, harvest), as the crop calendar gives it.

### AI

**Assistant**:
The portal's guide that answers readers' questions in words.
_Avoid_: chatbot, bot, copilot

**Fact**:
One value the portal holds, with the source it came from, that an AI answer may use.
_Avoid_: context, data point

**Grounded**:
Said of an AI answer whose every number can be traced to a fact.

**View action**:
A change to the view (open a section, pick a place, set the year, turn on a layer, show a forecast) that the assistant asks for when the reader wants to see something. The portal checks it against the catalogue and applies it at once through the view store, so the URL follows as for any other change.
_Avoid_: command, tool call

**Advisory**:
Written advice for one place and forecast period that joins district risk with crop stage. For now it remains an internal AI draft and cannot be exported or shared. If external distribution is added later, an officer must approve it first.
_Avoid_: bulletin, warning, alert

**Crop health screening**:
The portal's reading of a leaf or plant photo as a disease, pest or healthy class. A low-confidence screening is marked for expert review.
_Avoid_: diagnosis, detection
