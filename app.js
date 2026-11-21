const TOPICS = {
  'communism & class': ['communism','communist','socialism','socialist','class struggle','working class','capitalism','labor','labour','proletariat'],
  'fascism & nationalism': ['fascism','fascist','nazi','nationalism','authoritarian','revachol'],
  'race & colonialism': ['racism','racist','race','colonialism','colonial','imperialism','indigenous'],
  'gender & feminism': ['sexism','sexist','feminism','feminist','misogyny','gender','women'],
  'LGBTQ+ identities': ['lgbtq','queer','gay','lesbian','trans','nonbinary','bisexual','homophobia'],
  'culture & ideology': ['politics','political','ideology','discourse','culture','identity','representation']
};
const WORDS = {
  positive: new Set('love loved lovely great good hopeful hope solidarity beautiful joy joyful funny funny brilliant excellent happy proud inclusive freedom caring kind better enjoy enjoyed favorite favourite masterpiece'.split(' ')),
  negative: new Set('hate hated awful bad terrible fascist racism racist sexism sexist bigotry homophobia transphobia violence violent horrible worst depressing sad angry misery miserable corrupt cruel abuse oppressive oppression suffering failure fail'.split(' '))
};
const COLORS = {positive:'#66826c', neutral:'#d5ae55', negative:'#da6d45'};
const DEMO = [
  {author:'Participant 0001',text:'Disco Elysium understands that class is not an abstract idea; it shapes the choices people get to make. The writing still feels hopeful to me.',createdAt:'2025-02-14T12:00:00Z',topics:['communism & class','culture & ideology']},
  {author:'Participant 0002',text:'The game is so sharp about nationalism and the way authoritarian nostalgia gets dressed up as tradition.',createdAt:'2025-02-13T08:30:00Z',topics:['fascism & nationalism','culture & ideology']},
  {author:'Participant 0003',text:'I love how queer identities are present without every character becoming a lesson for the player.',createdAt:'2025-02-12T19:14:00Z',topics:['LGBTQ+ identities','culture & ideology']},
  {author:'Participant 0004',text:'Thinking about race, colonialism, and who gets to tell the history of Revachol. The game leaves a lot to discuss.',createdAt:'2025-02-11T14:05:00Z',topics:['race & colonialism','culture & ideology']},
  {author:'Participant 0001',text:'Some of the gender writing lands, some of it feels dated. I wish there were more women in the story.',createdAt:'2025-02-09T10:42:00Z',topics:['gender & feminism','culture & ideology']},
  {author:'Participant 0005',text:'Capitalism and misery are everywhere in this game, but the little moments of solidarity are beautiful.',createdAt:'2025-02-07T21:00:00Z',topics:['communism & class']},
  {author:'Participant 0006',text:'A fascinating game, though its treatment of racism and colonial history is complicated and sometimes uncomfortable.',createdAt:'2025-02-05T16:22:00Z',topics:['race & colonialism']},
  {author:'Participant 0003',text:'The political writing is brilliant; the humor makes the bleak parts feel human instead of hopeless.',createdAt:'2025-02-03T11:10:00Z',topics:['culture & ideology','fascism & nationalism']},
  {author:'Participant 0007',text:'Trans and nonbinary fans deserve better than people turning every conversation into a fight.',createdAt:'2025-02-01T09:00:00Z',topics:['LGBTQ+ identities','gender & feminism']},
  {author:'Participant 0008',text:'Nationalism is such a grim thread in Disco Elysium. The writing about it is painfully good.',createdAt:'2025-01-29T18:35:00Z',topics:['fascism & nationalism']},
  {author:'Participant 0002',text:'The game is messy on gender, and that is worth discussing without pretending there is one correct reading.',createdAt:'2025-01-26T13:25:00Z',topics:['gender & feminism','culture & ideology']},
  {author:'Participant 0009',text:'Communism in the game is funny, tragic, and more tender than I expected.',createdAt:'2025-01-22T07:45:00Z',topics:['communism & class']}
].map((d,i)=>({...d,id:`demo-${i}`,language:'en'}));

let posts = DEMO;
const filters = {topic:'all',sentiment:'all',range:'all'};
const $ = selector => document.querySelector(selector);
const clean = value => String(value ?? '').replace(/<[^>]*>/g, '');

function analyze(post) {
  const text = (post.text || '').toLowerCase();
  const words = text.match(/[\p{L}']+/gu) || [];
  let score = 0;
  for (const word of words) {
    if (WORDS.positive.has(word)) score += 1;
    if (WORDS.negative.has(word)) score -= 1;
  }
  const sentiment = score > 0 ? 'positive' : score < 0 ? 'negative' : 'neutral';
  const topics = Array.isArray(post.topics) && post.topics.length ? post.topics : Object.entries(TOPICS).filter(([, terms]) => terms.some(term => text.includes(term))).map(([topic]) => topic);
  return {...post, topics, score: words.length ? score / Math.sqrt(words.length) : 0, sentiment};
}
function filteredPosts() {
  const cutoff = filters.range === 'all' ? null : new Date(Date.now() - Number(filters.range) * 86400000);
  return posts.map(analyze).filter(p => {
    if (filters.topic !== 'all' && !p.topics.includes(filters.topic)) return false;
    if (filters.sentiment !== 'all' && p.sentiment !== filters.sentiment) return false;
    if (cutoff && (!p.createdAt || new Date(p.createdAt) < cutoff)) return false;
    return true;
  });
}
function setupTopics() {
  const select = $('#topic-filter');
  for (const topic of Object.keys(TOPICS)) {
    const option = document.createElement('option'); option.value = topic; option.textContent = topic; select.append(option);
  }
}
function renderMetrics(data) {
  $('#metric-posts').textContent = data.length.toLocaleString();
  $('#metric-authors').textContent = new Set(data.map(d => d.author).filter(Boolean)).size.toLocaleString();
  $('#metric-topics').textContent = new Set(data.flatMap(d => d.topics)).size;
  const avg = data.length ? d3.mean(data, d => d.score) : 0;
  const el = $('#metric-sentiment'); el.textContent = `${avg >= 0 ? '+' : ''}${avg.toFixed(2)}`; el.style.color = avg > .08 ? COLORS.positive : avg < -.08 ? COLORS.negative : '#a98736';
}
function baseSvg(container, height=210) {
  const node = document.querySelector(container); node.replaceChildren();
  const width = Math.max(280, node.clientWidth || 500);
  return {svg:d3.select(node).append('svg').attr('viewBox',`0 0 ${width} ${height}`).attr('preserveAspectRatio','xMinYMin meet'),width,height};
}
function renderTopics(data) {
  const {svg,width,height}=baseSvg('#topic-chart'); const margin={top:5,right:30,bottom:8,left:154};
  const counts=Object.keys(TOPICS).map(topic=>({topic,count:data.filter(p=>p.topics.includes(topic)).length}));
  const x=d3.scaleLinear().domain([0,d3.max(counts,d=>d.count)||1]).nice().range([margin.left,width-margin.right]);
  const y=d3.scaleBand().domain(counts.map(d=>d.topic)).range([margin.top,height-margin.bottom]).padding(.34);
  svg.append('g').attr('class','grid').attr('transform',`translate(0,${height-margin.bottom})`).call(d3.axisBottom(x).ticks(4).tickSize(-(height-margin.top-margin.bottom)).tickFormat(''));
  svg.append('g').attr('class','axis').attr('transform',`translate(${margin.left},0)`).call(d3.axisLeft(y).tickSize(0)).call(g=>g.select('.domain').remove());
  svg.selectAll('.topic-bar').data(counts).join('rect').attr('class','topic-bar').attr('x',margin.left).attr('y',d=>y(d.topic)).attr('height',y.bandwidth()).attr('width',d=>Math.max(0,x(d.count)-margin.left));
  svg.selectAll('.bar-label').data(counts).join('text').attr('class','bar-label').attr('x',d=>x(d.count)+6).attr('y',d=>y(d.topic)+y.bandwidth()/2+3).text(d=>d.count);
}
function renderSentiment(data) {
  const {svg,width,height}=baseSvg('#sentiment-chart'); const counts=['positive','neutral','negative'].map(name=>({name,count:data.filter(d=>d.sentiment===name).length}));
  const total=d3.sum(counts,d=>d.count); const cx=width/2,cy=height/2-3,r=Math.min(72,width*.23);
  const arc=d3.arc().innerRadius(r*.63).outerRadius(r);
  const pie=d3.pie().sort(null).value(d=>d.count || (total ? 0 : 1));
  svg.append('g').attr('transform',`translate(${cx},${cy})`).selectAll('path').data(pie(counts)).join('path').attr('d',arc).attr('fill',d=>COLORS[d.data.name]).attr('stroke','#fbfaf6').attr('stroke-width',3);
  svg.append('text').attr('x',cx).attr('y',cy-1).attr('text-anchor','middle').attr('fill','#242921').attr('font-family','Space Grotesk').attr('font-weight',600).attr('font-size',24).text(total);
  svg.append('text').attr('x',cx).attr('y',cy+15).attr('text-anchor','middle').attr('fill','#777a70').attr('font-family','DM Mono').attr('font-size',8).text('POSTS');
  const legend=d3.select('#sentiment-chart').append('div').attr('class','sentiment-legend');
  legend.selectAll('span').data(counts).join('span').html(d=>`<i class="dot ${d.name}"></i>${d.name} ${total ? Math.round(d.count/total*100) : 0}%`);
}
function renderTimeline(data) {
  const {svg,width,height}=baseSvg('#timeline-chart',190); const margin={top:8,right:15,bottom:28,left:34};
  const dated=data.filter(d=>d.createdAt && !Number.isNaN(new Date(d.createdAt).getTime()));
  const grouped=d3.rollups(dated,d=>d.length,d=>d3.utcDay(new Date(d.createdAt)).toISOString()).map(([date,count])=>({date:new Date(date),count})).sort((a,b)=>a.date-b.date);
  if (!grouped.length) { svg.append('text').attr('x',width/2).attr('y',95).attr('text-anchor','middle').attr('fill','#777a70').attr('font-family','DM Mono').attr('font-size',11).text('No dated posts in this view'); return; }
  const x=d3.scaleUtc().domain(d3.extent(grouped,d=>d.date)).range([margin.left,width-margin.right]);
  if (+x.domain()[0]===+x.domain()[1]) x.domain([new Date(+x.domain()[0]-86400000),new Date(+x.domain()[1]+86400000)]);
  const y=d3.scaleLinear().domain([0,d3.max(grouped,d=>d.count)||1]).nice().range([height-margin.bottom,margin.top]);
  svg.append('g').attr('class','grid').attr('transform',`translate(${margin.left},0)`).call(d3.axisLeft(y).ticks(4).tickSize(-(width-margin.left-margin.right)).tickFormat(''));
  svg.append('g').attr('class','axis').attr('transform',`translate(0,${height-margin.bottom})`).call(d3.axisBottom(x).ticks(5).tickFormat(d3.utcFormat('%b %d')));
  svg.append('g').attr('class','axis').attr('transform',`translate(${margin.left},0)`).call(d3.axisLeft(y).ticks(4).tickSize(0)).call(g=>g.select('.domain').remove());
  svg.append('path').datum(grouped).attr('fill','none').attr('stroke','#66826c').attr('stroke-width',2.5).attr('d',d3.line().x(d=>x(d.date)).y(d=>y(d.count)).curve(d3.curveMonotoneX));
  svg.selectAll('.point').data(grouped).join('circle').attr('cx',d=>x(d.date)).attr('cy',d=>y(d.count)).attr('r',3).attr('fill','#da6d45');
}
function renderTable(data) {
  const rows=[...data].sort((a,b)=>new Date(b.createdAt||0)-new Date(a.createdAt||0)).slice(0,30);
  const body=d3.select('#posts-table'); body.selectAll('tr').data(rows, d=>d.id || `${d.author}-${d.createdAt}-${d.text}`).join('tr').html(d=>{
    const excerpt=clean(d.text||'').slice(0,220)+(String(d.text||'').length>220?'…':'');
    const tags=d.topics.map(t=>`<span class="tag">${clean(t)}</span>`).join('');
    const date=d.createdAt && !Number.isNaN(new Date(d.createdAt).getTime()) ? d3.utcFormat('%Y-%m-%d')(new Date(d.createdAt)) : '—';
    return `<td>${clean(excerpt)}</td><td>${tags||'—'}</td><td><span class="sentiment-pill ${d.sentiment}">${d.sentiment} · ${d.score.toFixed(2)}</span></td><td>${date}</td><td>${clean(d.author||'Unknown')}</td>`;
  });
  if (!rows.length) body.html('<tr><td colspan="5">No posts match these filters.</td></tr>');
}
function render() {
  const data=filteredPosts(); renderMetrics(data); renderTopics(data); renderSentiment(data); renderTimeline(data); renderTable(data);
}
function pseudonymize(input) {
  const authors=new Map();
  return input.map((post,i)=>{
    const key=post.author || post.handle || post.did || `unknown-${i}`;
    if (!authors.has(key)) authors.set(key,`Participant ${String(authors.size+1).padStart(4,'0')}`);
    const copy={...post,author:authors.get(key)};
    delete copy.handle; delete copy.did; delete copy.uri;
    return copy;
  });
}
async function importFile(file) {
  try {
    const payload=JSON.parse(await file.text()); const items=Array.isArray(payload)?payload:payload.posts;
    if (!Array.isArray(items)) throw new Error('Expected a JSON array or an object containing a posts array.');
    posts=pseudonymize(items); $('#data-status').textContent=`Imported ${posts.length.toLocaleString()} posts · local only`; render();
  } catch(error) { alert(`Could not read this collection: ${error.message}`); }
}
function loadDemo() { posts=DEMO; $('#data-status').textContent='Synthetic demo data'; $('#topic-filter').value='all'; $('#sentiment-filter').value='all'; $('#range-filter').value='all'; Object.assign(filters,{topic:'all',sentiment:'all',range:'all'}); render(); }
setupTopics();
for (const [id,key] of [['topic-filter','topic'],['sentiment-filter','sentiment'],['range-filter','range']]) $(`#${id}`).addEventListener('change',event=>{filters[key]=event.target.value;render();});
$('#file-input').addEventListener('change',event=>{if(event.target.files[0]) importFile(event.target.files[0]);event.target.value='';});
$('#demo-button').addEventListener('click',loadDemo);
$('#dismiss-notice').addEventListener('click',()=>$('.notice').remove());
let resizeTimer; window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(render,120);});
render();
