// Applies Better Auth's schema (user, session, account, verification,
// organization, member, invitation, ...) to the database configured in
// ../lib/auth.ts. Safe to re-run: it only creates what is missing.
//
// Run from frontend/:  node scripts/migrate-auth.mjs
// (or: npm run db:migrate-auth)
//
// NOTE: the DB path depends on cwd, exactly like the dev server — both must
// run from frontend/ so they resolve the same ../anvaya_auth.db file.

import { getMigrations } from "better-auth/db/migration";

const { auth } = await import("../lib/auth.ts");

const plan = await getMigrations(auth.options, { throwOnUnsafe: true });

if (plan.toBeCreated.length) {
  console.log("tables to create:", plan.toBeCreated.map((t) => t.table).join(", "));
}
if (plan.toBeAdded.length) {
  console.log(
    "columns to add:",
    plan.toBeAdded.map((c) => `${c.table}.${Object.keys(c.fields).join(",")}`).join(", ")
  );
}
if (plan.toBeAddedIndexes.length) {
  console.log("indexes to add:", plan.toBeAddedIndexes.map((i) => i.name).join(", "));
}
if (plan.unsafeChanges.length) {
  console.warn("unsafe changes skipped:", plan.unsafeChanges);
}

await plan.runMigrations();

if (!plan.toBeCreated.length && !plan.toBeAdded.length && !plan.toBeAddedIndexes.length) {
  console.log("Better Auth schema is already up to date.");
} else {
  console.log("Better Auth migration applied.");
}
