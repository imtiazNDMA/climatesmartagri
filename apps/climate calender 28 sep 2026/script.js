const records = [
  {
    province: 'Punjab',
    crop: 'Wheat',
    traditional: 'Oct–Dec sowing → Mar–Apr harvest',
    adjusted: 'Oct–Nov sowing → Mar–Apr harvest',
    reason: 'Rising temperatures and terminal heat during grain filling can reduce yield; timely sowing helps the crop mature before severe spring heat.'
  },
  {
    province: 'Punjab',
    crop: 'Rice',
    traditional: 'May–Jul → Sep–Oct',
    adjusted: 'May–Jun → Sep–Oct',
    reason: 'Earlier establishment can reduce exposure to late-season heat and improve synchronization with water availability.'
  },
  {
    province: 'Punjab',
    crop: 'Cotton',
    traditional: 'Apr–Jun → Sep–Nov',
    adjusted: 'Apr–May → Aug–Oct/Nov',
    reason: 'High temperature and water stress during flowering/boll development can affect yield; timely sowing reduces heat exposure.'
  },
  {
    province: 'Punjab',
    crop: 'Maize – Spring',
    traditional: 'Jan–Feb → May–Jun',
    adjusted: 'Jan–Feb → May–Jun',
    reason: 'Increasing spring temperatures can expose grain filling to heat; timely sowing helps avoid the hottest period.'
  },
  {
    province: 'Punjab',
    crop: 'Maize – Kharif',
    traditional: 'Jun–Jul → Sep–Oct',
    adjusted: 'Jun–early Jul → Sep–Oct',
    reason: 'Increasing heat and rainfall variability during reproductive stages require better synchronization with available moisture.'
  },
  {
    province: 'Punjab',
    crop: 'Sugarcane',
    traditional: 'Feb–Mar / Sep–Oct',
    adjusted: 'Feb–Mar / Sep–Oct',
    reason: 'Calendar remains broadly similar, but higher temperatures and water demand require efficient irrigation and heat management.'
  },
  {
    province: 'Sindh',
    crop: 'Wheat',
    traditional: 'Nov–Dec → Mar–Apr',
    adjusted: 'Nov–early Dec → Mar–Apr',
    reason: 'Warmer winter/spring conditions increase the risk of heat during grain filling; avoid delayed sowing.'
  },
  {
    province: 'Sindh',
    crop: 'Rice',
    traditional: 'Jun–Jul → Sep–Oct',
    adjusted: 'Jun → Sep–Oct',
    reason: 'Earlier establishment improves water-use planning and reduces exposure to late-season heat/rainfall variability.'
  },
  {
    province: 'Sindh',
    crop: 'Cotton',
    traditional: 'Apr–Jun → Sep–Nov',
    adjusted: 'Apr–May → Aug–Oct/Nov',
    reason: 'Extreme heat and water stress can affect flowering and boll development; earlier sowing reduces exposure.'
  },
  {
    province: 'Sindh',
    crop: 'Maize',
    traditional: 'Jun–Jul → Sep–Oct',
    adjusted: 'Jun–early Jul → Sep–Oct',
    reason: 'Avoid reproductive/grain-filling stages during periods of extreme heat and moisture stress.'
  },
  {
    province: 'Sindh',
    crop: 'Sugarcane',
    traditional: 'Feb–Mar / Sep–Oct',
    adjusted: 'Feb–Mar / Sep–Oct',
    reason: 'Very high-water requirement makes water-use efficiency more important under increasing heat and water stress.'
  },
  {
    province: 'KP',
    crop: 'Wheat',
    traditional: 'Oct–Dec → Mar–Apr',
    adjusted: 'Oct–Nov → Mar–Apr',
    reason: 'Warmer spring conditions can accelerate maturity and increase terminal heat; timely sowing protects grain filling.'
  },
  {
    province: 'KP',
    crop: 'Maize',
    traditional: 'Feb–Apr / Jun–Jul',
    adjusted: 'Feb–Mar / Jun–Jul',
    reason: 'Temperature variability and heat during reproductive stages can reduce grain formation.'
  },
  {
    province: 'KP',
    crop: 'Rice',
    traditional: 'May–Jul → Sep–Oct',
    adjusted: 'May–Jun → Sep–Oct',
    reason: 'Better synchronization with rainfall and irrigation while reducing exposure to late-season climatic variability.'
  },
  {
    province: 'KP',
    crop: 'Tobacco',
    traditional: 'Feb–Mar → May–Jun',
    adjusted: 'Feb–Mar → May–Jun',
    reason: 'Calendar largely retained; emphasis shifts toward heat, moisture and disease management.'
  },
  {
    province: 'Baluchistan',
    crop: 'Wheat',
    traditional: 'Oct–Dec → Mar–Apr',
    adjusted: 'Oct–Nov → Mar–Apr',
    reason: 'Increasing temperature and rainfall uncertainty make timely establishment important, particularly where moisture is limited.'
  },
  {
    province: 'Baluchistan',
    crop: 'Rice',
    traditional: 'May–Jul → Sep–Oct',
    adjusted: 'May–Jun → Sep–Oct',
    reason: 'Limited water availability requires synchronization with irrigation supply; mainly applicable to irrigated areas.'
  },
  {
    province: 'Baluchistan',
    crop: 'Cotton',
    traditional: 'Apr–Jun → Sep–Nov',
    adjusted: 'Apr–May → Aug–Oct',
    reason: 'High temperatures and water scarcity increase crop stress; earlier establishment can reduce exposure during critical stages.'
  },
  {
    province: 'Baluchistan',
    crop: 'Maize',
    traditional: 'Mar–Apr / Jun–Jul',
    adjusted: 'Mar–Apr / Jun–Jul',
    reason: 'Climate variability is high; adjustment should be location-specific and linked to rainfall/soil moisture.'
  },
  {
    province: 'Baluchistan',
    crop: 'Orchards',
    traditional: 'Traditional regional schedule',
    adjusted: 'Climate-risk adjusted',
    reason: 'Warmer winters may affect chilling requirements, flowering and fruit development; orchard management needs location-specific adjustment.'
  }
];

const provinceOrder = ['All', 'Punjab', 'Sindh', 'KP', 'Baluchistan'];
let currentProvince = 'All';

const kpiGrid = document.getElementById('kpiGrid');
const provinceFilters = document.getElementById('provinceFilters');
const calendarBody = document.getElementById('calendarBody');
const resultCount = document.getElementById('resultCount');
const searchInput = document.getElementById('searchInput');

function uniqueProvinces() {
  return [...new Set(records.map((record) => record.province))];
}

function summaryCards() {
  const provinces = uniqueProvinces().length;
  const crops = [...new Set(records.map((record) => record.crop))].length;
  const adjustedCount = records.filter((record) => record.traditional !== record.adjusted).length;
  const priorityThemes = ['Heat stress', 'Water management', 'Timely sowing'];

  return [
    { label: 'Provinces', value: provinces, note: 'Climate adaptation zones monitored' },
    { label: 'Crops tracked', value: crops, note: 'Seasonal decision points reviewed' },
    { label: 'Adjusted calendars', value: adjustedCount, note: 'Crop schedules shifted for risk reduction' },
    { label: 'Interventions', value: priorityThemes.length, note: 'Key adaptation actions prioritized' }
  ];
}

function renderKpis() {
  const cards = summaryCards();
  kpiGrid.innerHTML = cards
    .map(
      (card) => `
        <article class="kpi-card">
          <span class="label">${card.label}</span>
          <div class="value">${card.value}</div>
          <span class="note">${card.note}</span>
        </article>
      `
    )
    .join('');
}

function renderProvinceFilters() {
  const buttons = provinceOrder
    .map(
      (province) => `
        <button class="filter-btn ${province === currentProvince ? 'active' : ''}" data-province="${province}">
          ${province}
        </button>
      `
    )
    .join('');

  provinceFilters.innerHTML = buttons;

  provinceFilters.querySelectorAll('.filter-btn').forEach((button) => {
    button.addEventListener('click', () => {
      currentProvince = button.dataset.province;
      renderProvinceFilters();
      renderTable();
    });
  });
}

function getFilteredRecords() {
  const searchValue = searchInput.value.trim().toLowerCase();

  return records.filter((record) => {
    const matchesProvince = currentProvince === 'All' || record.province === currentProvince;
    const searchText = `${record.province} ${record.crop} ${record.traditional} ${record.adjusted} ${record.reason}`.toLowerCase();
    const matchesSearch = !searchValue || searchText.includes(searchValue);
    return matchesProvince && matchesSearch;
  });
}

function renderTable() {
  const filtered = getFilteredRecords();
  resultCount.textContent = `${filtered.length} record${filtered.length === 1 ? '' : 's'}`;

  if (!filtered.length) {
    calendarBody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align:center; color: var(--muted); padding: 34px 16px;">
          No crop calendar entries match the selected filters.
        </td>
      </tr>
    `;
    return;
  }

  calendarBody.innerHTML = filtered
    .map(
      (record) => `
        <tr>
          <td>
            <span class="province-badge ${record.province.toLowerCase().replace(/\s+/g, '-')}">
              ${record.province}
            </span>
          </td>
          <td class="crop-name">${record.crop}</td>
          <td>${record.traditional}</td>
          <td><span class="calendar-callout">${record.adjusted}</span></td>
          <td class="reason">${record.reason}</td>
        </tr>
      `
    )
    .join('');
}

searchInput.addEventListener('input', renderTable);

renderKpis();
renderProvinceFilters();
renderTable();
