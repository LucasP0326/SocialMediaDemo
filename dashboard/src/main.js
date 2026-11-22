import * as d3 from "d3";
import "./style.css";

const tones = ["negative", "neutral", "positive"];
const color = d3.scaleOrdinal(tones, ["#e68a74", "#d2bb91", "#9fcabd"]);
const total = counts => d3.sum(Object.values(counts));
const format = d3.format(",");
const monthDate = d3.utcParse("%Y-%m");
const monthName = d3.utcFormat("%b %Y");
const lens = document.querySelector("#lens");
const year = document.querySelector("#year");
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

function timeline(rows, periods, group, label, unit) {
  const host = d3.select("#timeline");
  host.selectAll("*").remove();
  if (!rows.length) {
    host.append("p").attr("class", "empty").text("No posts match these filters.");
    return;
  }
  const grouped = summarize(rows, group);
  const values = periods.map(key => ({key, counts: grouped.get(key) ?? {}}));
  const width = 560;
  const height = 310;
  const x = d3.scalePoint(periods, [42, width - 22]).padding(0.35);
  const y = d3.scaleLinear([0, d3.max(values, row => d3.max(tones, tone => row.counts[tone] ?? 0))],
    [height - 40, 15]).nice();
  const svg = host.append("svg").attr("viewBox", `0 0 ${width} ${height}`)
    .attr("role", "img").attr("aria-label", `Post counts by ${unit} and sentiment`);
  const ticks = periods.filter((_, index) => index % Math.ceil(periods.length / 8) === 0);
  svg.append("g").attr("transform", `translate(0,${height - 40})`)
    .call(d3.axisBottom(x).tickValues(ticks).tickFormat(label));
  svg.append("g").attr("class", "gridlines").attr("transform", "translate(42,0)")
    .call(d3.axisLeft(y).ticks(5).tickSize(64 - width).tickFormat(d3.format("~g")));
  for (const tone of tones) {
    svg.append("path").datum(values).attr("fill", "none").attr("stroke", color(tone))
      .attr("stroke-width", 2.5).attr("d", d3.line()
        .x(row => x(row.key)).y(row => y(row.counts[tone] ?? 0)));
    svg.selectAll(null).data(values).join("circle")
      .attr("cx", row => x(row.key)).attr("cy", row => y(row.counts[tone] ?? 0))
      .attr("r", 4).attr("fill", color(tone)).append("title")
      .text(row => `${label(row.key)} · ${tone}: ${row.counts[tone] ?? 0}`);
  }
  const table = host.append("details").attr("class", "chart-data");
  table.append("summary").text(`View counts by ${unit}`);
  const grid = table.append("table");
  grid.append("thead").append("tr").selectAll("th").data([unit, ...tones]).join("th")
    .attr("scope", "col").text(label => label);
  const body = grid.append("tbody").selectAll("tr").data(values).join("tr");
  body.append("th").attr("scope", "row").text(row => label(row.key));
  body.selectAll("td").data(row => tones.map(tone => row.counts[tone] ?? 0)).join("td").text(value => value);
}

function show(data) {
  const first = d3.utcMonth.floor(new Date(data.since));
  const last = d3.utcMonth.ceil(new Date(data.until));
  const months = d3.utcMonth.range(first, last).map(d3.utcFormat("%Y-%m"));
  const includesGeneral = data.search?.includesGeneralDiscussion;
  const lensOptions = includesGeneral ? ["Any research lens", ...data.lenses] : data.lenses;
  options(lens, lensOptions, includesGeneral ? "All game discussion" : "All lenses");
  const yearOf = key => key.slice(0, 4);
  const years = [...new Set(months.map(yearOf))];
  const formatMonth = key => monthName(monthDate(key));
  options(year, years, "All years");

  function updateMonths() {
    const available = months.filter(key => yearOf(key) === year.value);
    options(month, available, "All months", formatMonth);
    month.value = "";
    month.disabled = !year.value;
    return available;
  }
  let monthsInYear = updateMonths();
  const fromFeeds = data.search?.communityFeeds;
  d3.select("#source").text(data.source === "synthetic" ? "Synthetic demo data" :
    fromFeeds ? "Public Bluesky community-feed sample" : "Public Bluesky search sample");
  d3.select("#window").text(`${data.since} to ${data.until} (end excluded · UTC)`);
  d3.select("#accounts").text(format(data.accounts));
  d3.select("#coverage").text(fromFeeds
    ? `Collected ${data.search.collectedOn} (UTC) from ${fromFeeds} community feeds across ${data.search.pages} pages. Feed posts matched the game or a named character or location in text or image descriptions. ${data.search.threadsRead ?? 0} of ${data.search.threadsAttempted ?? 0} queried threads were read, adding ${format(data.search.additionalReplies ?? 0)} unique English-tagged replies before date and text filtering. A bounded author-feed search added ${format(data.search.archivalPosts ?? 0)} posts from 2023. Feed, thread, and archive selection limit coverage.`
    : data.search?.importedPages
    ? `Imported ${data.search.importedPages} Bluesky search response pages containing ${format(data.candidates)} unique candidate posts. Coverage depends on the queries, dates, and cursors used to collect those pages.`
    : data.search
    ? `Bluesky English-language search returned ${format(data.candidates)} unique candidate posts across ${data.search.queries} queries and ${data.search.pages} pages. ${data.search.queriesAtPageLimit} queries reached the configured page cap with more results available. Search indexing and query coverage limit the sample.`
    : "Every observation in this demo is synthetic. The charts illustrate the workflow.");
  d3.selectAll(".legend").selectAll("span").data(tones).join("span")
    .style("--swatch", color).text(tone => tone);

  function render() {
    const rows = data.cells.filter(row =>
      (!lens.value || row.lenses.includes(lens.value) ||
        (lens.value === "Any research lens" && row.lenses.length > 0)) &&
      (!year.value || yearOf(row.month) === year.value) &&
      (!month.value || row.month === month.value));
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
    const unit = year.value ? "month" : "year";
    d3.select("#timeline-description").text(`Sampled post volume by sentiment and ${unit}.`);
    if (year.value) {
      timeline(rows, month.value ? [month.value] : monthsInYear, row => row.month, formatMonth, unit);
    } else {
      timeline(rows, years, row => yearOf(row.month), key => key, unit);
    }
  }

  lens.addEventListener("change", render);
  year.addEventListener("change", () => {
    monthsInYear = updateMonths();
    render();
  });
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
