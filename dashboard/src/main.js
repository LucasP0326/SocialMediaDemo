import * as d3 from "d3";
import "./style.css";

const tones = ["negative", "neutral", "positive"];
const color = d3.scaleOrdinal(tones, ["#e68a74", "#d2bb91", "#9fcabd"]);
const total = counts => d3.sum(Object.values(counts));
const format = d3.format(",");
const monthDate = d3.utcParse("%Y-%m");
const monthName = d3.utcFormat("%b %Y");
const lens = document.querySelector("#lens");
const month = document.querySelector("#month");

function options(select, values, all, label = value => value) {
  d3.select(select).selectAll("option").data(["", ...values]).join("option")
    .attr("value", value => value)
    .text(value => value ? label(value) : all);
}

function summarize(rows, key) {
  return d3.rollup(rows, group => Object.fromEntries(
    tones.map(tone => [tone, d3.sum(group, row => row.counts[tone] ?? 0)]),
  ), key);
}

function bars(selector, data, keys) {
  const host = d3.select(selector);
  host.selectAll("*").remove();
  if (!data.length) {
    host.append("p").attr("class", "empty").text("No posts match these filters.");
    return;
  }
  const scale = d3.scaleLinear([0, d3.max(data, row => total(row.counts))], [0, 100]);
  const rows = host.selectAll(".bar-row").data(data).join("div").attr("class", "bar-row");
  const header = rows.append("div").attr("class", "bar-label");
  header.append("span").text(row => row.label);
  header.append("strong").text(row => format(total(row.counts)));
  const tracks = rows.append("div").attr("class", "track")
    .attr("role", "img").attr("aria-label", row => keys.map(
      key => `${key}: ${row.counts[key] ?? 0}`,
    ).join(", "));
  tracks.selectAll("span").data(row => keys.map(key => ({key, count: row.counts[key] ?? 0})))
    .join("span").style("width", item => `${scale(item.count)}%`)
    .style("background", item => keys.length === 1 ? "#9fcabd" : color(item.key))
    .attr("title", item => `${item.key}: ${item.count}`);
}

function timeline(rows, months) {
  const host = d3.select("#timeline");
  host.selectAll("*").remove();
  if (!rows.length) {
    host.append("p").attr("class", "empty").text("No posts match these filters.");
    return;
  }
  const byMonth = summarize(rows, row => row.month);
  const values = months.map(key => ({key, counts: byMonth.get(key) ?? {}}));
  const width = 560;
  const height = 310;
  const x = d3.scalePoint(months, [42, width - 22]).padding(0.35);
  const y = d3.scaleLinear([0, d3.max(values, row => d3.max(tones, tone => row.counts[tone] ?? 0))],
    [height - 40, 15]).nice();
  const svg = host.append("svg").attr("viewBox", `0 0 ${width} ${height}`)
    .attr("role", "img").attr("aria-label", "Monthly post counts for each sentiment");
  const ticks = months.filter((_, index) => index % Math.ceil(months.length / 6) === 0);
  svg.append("g").attr("transform", `translate(0,${height - 40})`)
    .call(d3.axisBottom(x).tickValues(ticks).tickFormat(key => monthName(monthDate(key))));
  svg.append("g").attr("class", "gridlines").attr("transform", "translate(42,0)")
    .call(d3.axisLeft(y).ticks(5).tickSize(64 - width).tickFormat(d3.format("~g")));
  for (const tone of tones) {
    svg.append("path").datum(values).attr("fill", "none").attr("stroke", color(tone))
      .attr("stroke-width", 2.5).attr("d", d3.line()
        .x(row => x(row.key)).y(row => y(row.counts[tone] ?? 0)));
    svg.selectAll(null).data(values).join("circle")
      .attr("cx", row => x(row.key)).attr("cy", row => y(row.counts[tone] ?? 0))
      .attr("r", 4).attr("fill", color(tone)).append("title")
      .text(row => `${monthName(monthDate(row.key))} · ${tone}: ${row.counts[tone] ?? 0}`);
  }
  const table = host.append("details").attr("class", "chart-data");
  table.append("summary").text("View monthly counts");
  const grid = table.append("table");
  grid.append("thead").append("tr").selectAll("th").data(["Month", ...tones]).join("th")
    .attr("scope", "col").text(label => label);
  const body = grid.append("tbody").selectAll("tr").data(values).join("tr");
  body.append("th").attr("scope", "row").text(row => monthName(monthDate(row.key)));
  body.selectAll("td").data(row => tones.map(tone => row.counts[tone] ?? 0)).join("td").text(value => value);
}

function show(data) {
  const first = d3.utcMonth.floor(new Date(data.since));
  const last = d3.utcMonth.ceil(new Date(data.until));
  const months = d3.utcMonth.range(first, last).map(d3.utcFormat("%Y-%m"));
  options(lens, data.lenses, "All lenses");
  options(month, months, "All months", key => monthName(monthDate(key)));
  d3.select("#source").text(data.source === "synthetic" ? "Synthetic demo data" : "Public Bluesky search sample");
  d3.select("#window").text(`${data.since} to ${data.until} (end excluded · UTC)`);
  d3.select("#accounts").text(format(data.accounts));
  d3.select("#coverage").text(data.search?.importedPages
    ? `Imported ${data.search.importedPages} Bluesky search response pages containing ${format(data.candidates)} unique candidate posts. Coverage depends on the queries, dates, and cursors used to collect those pages.`
    : data.search
    ? `Bluesky English-language search returned ${format(data.candidates)} unique candidate posts across ${data.search.queries} queries and ${data.search.pages} pages. ${data.search.queriesAtPageLimit} queries reached the configured page cap with more results available. Search indexing and query coverage limit the sample.`
    : "Every observation in this demo is synthetic. The charts illustrate the workflow.");
  d3.selectAll(".legend").selectAll("span").data(tones).join("span")
    .style("--swatch", color).text(tone => tone);

  function render() {
    const rows = data.cells.filter(row =>
      (!lens.value || row.lenses.includes(lens.value)) && (!month.value || row.month === month.value));
    const byTopic = summarize(rows, row => row.topic);
    d3.select("#posts").text(format(d3.sum(rows, row => total(row.counts))));
    d3.select("#topics").text([...byTopic.keys()].filter(id => id >= 0).length);
    const orderedTopics = [...data.topics, {id: -1, terms: ["Unassigned"]}];
    bars("#topic-chart", orderedTopics.filter(topic => byTopic.has(topic.id)).map(topic => ({
      label: topic.terms.join(" · "), counts: byTopic.get(topic.id),
    })), tones);
    bars("#lens-chart", data.lenses.map(label => ({label, counts: {
      posts: d3.sum(rows.filter(row => row.lenses.includes(label)), row => total(row.counts)),
    }})).filter(row => total(row.counts)).sort((a, b) => total(b.counts) - total(a.counts)), ["posts"]);
    timeline(rows, month.value ? [month.value] : months);
  }

  lens.addEventListener("change", render);
  month.addEventListener("change", render);
  render();
  document.querySelector("#dashboard").hidden = false;
}

d3.json(`${import.meta.env.BASE_URL}research.json`).then(show).catch(() => {
  document.querySelector("#source").textContent = "Dataset unavailable";
  const error = document.querySelector("#error");
  error.textContent = "Generate research data with python research.py --demo or run a Bluesky collection, then reload.";
  error.hidden = false;
});
