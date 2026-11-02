// PostgreSQL SQL smoke tests via PGlite; not a multi-session Docker/dbt integration test.
import { PGlite } from '@electric-sql/pglite';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
process.on('uncaughtException', e => { console.error(e.message); process.exit(1); });
const db = new PGlite();
const read = p => readFileSync(resolve(root, p), 'utf8');
const scalar = async sql => Object.values((await db.query(sql)).rows[0])[0];
async function legacy(name) {
  // psql display commands have no SQL semantics and are omitted in this harness.
  await db.exec(read('tests/dbt/legacy_sql/'+name).split('\n').filter(l => !l.startsWith('\\')).join('\n'));
}
console.log(await scalar('select version()'));
for (const name of ['001_create_schemas.sql','002_postgres_loader.sql']) await legacy(name);
const columns = (await db.query("select column_name from information_schema.columns where table_schema='staging' and table_name='iowa_sales_exact' order by ordinal_position")).rows.map(x=>x.column_name);
for (const [id,date,sales] of [[1,'2024-07-01','12.34'],[2,'2025-07-01','24.68'],[3,'2025-11-01','25']]) {
 const row = Object.fromEntries(columns.map(c=>[c,'']));
 Object.assign(row,{_audit_row_id:id,invoice_id:'same',ordered_on:date,store_no:'001',item_no:'01',
  bottle_volume_ml:'750',sales_bottles:'2',state_bottle_retail:'12.34',sales_dollars:sales,sales_liters:'1.5'});
 await db.query(`insert into staging.iowa_sales_exact values (${columns.map((_,i)=>'$'+(i+1)).join(',')})`,columns.map(c=>row[c]));
}
for(const name of ['003_typed_views.sql','005_reconciliation_views.sql','006_build_marts.sql','007_monthly_kpis.sql','008_powerbi_access.sql']) await legacy(name);
await db.exec(read('warehouse/postgres/009_dbt_access.sql'));
await db.exec('set role retail_dbt');
let functions = read('dbt/macros/initialize_conversions.sql');
functions = functions.slice(functions.indexOf('CREATE OR REPLACE FUNCTION'), functions.indexOf('{% endmacro'));
await db.exec(functions.replaceAll('{{ target.schema }}','dbt_dev'));
const tables = new Set(['fact_sales','dim_store','dim_product','dim_date','sales_monthly']);
const models = ['stg_iowa_sales','int_sales_reconciled','fact_sales','dim_store','dim_product','dim_date','sales_monthly','v_sales_monthly_kpis','bi_sales_monthly'];
for(const name of models) {
 const sql = read('dbt/models/'+name+'.sql').replace(/\{\{ config\([^\n]*\) \}\}/g,'')
  .replaceAll('{{ target.schema }}','dbt_dev').replace(/\{\{ ref\('([^']+)'\) \}\}/g, 'dbt_dev.$1')
  .replace("{{ source('iowa', 'sales_exact') }}",'staging.iowa_sales_exact');
 await db.exec(`create ${tables.has(name)?'table':'view'} dbt_dev.${name} as ${sql}`);
}
await db.exec('reset role');
const before = await scalar('select jsonb_agg(to_jsonb(t) order by month_start)::text from marts.bi_sales_monthly t');
await db.exec(read('warehouse/postgres/010_publication.sql'));
assert.equal(await scalar('select jsonb_agg(to_jsonb(t) order by month_start)::text from marts.bi_sales_monthly t'), before);
const original = await scalar('select snapshot_id::text from publication.current_snapshot');
await db.exec('set role retail_publisher; begin; lock table staging.iowa_sales_exact, ops.pg_loaded_exports in share mode;');
for(const name of models) await db.exec(`lock table dbt_dev.${name} in access share mode`);
for(const name of tables) await db.exec(`lock table dbt_dev.${name} in share mode`);
await db.exec('rollback');
const id='11111111-1111-4111-8111-111111111111';
const biColumns=(await db.query("select column_name from information_schema.columns where table_schema='dbt_dev' and table_name='bi_sales_monthly' order by ordinal_position")).rows.map(x=>x.column_name);
assert.equal(biColumns.length,41);
await db.exec(`begin; insert into publication.snapshots values ('${id}',clock_timestamp(),'DBT_VALIDATED',repeat('a',64),'{}','{}',3);
 insert into publication.monthly_snapshots select '${id}',${biColumns.map(c=>c==='kpi_snapshot_validated_at'?'clock_timestamp()':'v.'+c).join(',')} from dbt_dev.bi_sales_monthly v;
 update publication.current_snapshot set snapshot_id='${id}',switched_at=clock_timestamp(); commit;`);
assert.equal(await scalar('select snapshot_id::text from publication.current_snapshot'),id);
const published = await scalar("select jsonb_agg(to_jsonb(t)-'kpi_snapshot_validated_at' order by month_start)::text from publication.monthly_snapshots t where _snapshot_id='"+id+"'");
await db.exec(`begin; update publication.current_snapshot set snapshot_id='${original}';`);
try { await db.exec(`insert into publication.snapshots values ('${id}',clock_timestamp(),'DBT_VALIDATED',repeat('a',64),'{}','{}',3)`); assert.fail('Expected duplicate key'); }
catch(e) { assert.match(e.message,/duplicate key/); await db.exec('rollback'); }
assert.equal(await scalar('select snapshot_id::text from publication.current_snapshot'),id);
await db.exec(`begin; update publication.current_snapshot set snapshot_id='${original}'; commit;`);
assert.equal(await scalar('select snapshot_id::text from publication.current_snapshot'),original);
await db.exec('reset role; set role retail_bi');
assert.equal(await scalar('select count(*)::int from marts.bi_sales_monthly'),3);
try { await db.query('select * from publication.monthly_snapshots'); assert.fail('BI should not read storage directly'); }
catch(e) { assert.match(e.message,/permission denied/); }
await db.exec('reset role; set role retail_publisher');
try { await db.exec("update staging.iowa_sales_exact set sales_dollars='0'"); assert.fail('Publisher should not update source'); }
catch(e) { assert.match(e.message,/permission denied/); }
await db.exec('reset role; set role retail_dbt; create table dbt_dev.future_table(id integer); reset role;');
assert.equal(await scalar("select has_table_privilege('retail_publisher','dbt_dev.future_table','MAINTAIN')"),true);
assert.equal(await scalar("select has_table_privilege('retail_publisher','dbt_dev.future_table','SELECT')"),true);
console.log('PASS: bootstrap preservation, 41-column contract, publisher locks/permissions, publication switch, failed-transaction rollback, explicit rollback, BI access, future dbt grants.');
await db.close();
