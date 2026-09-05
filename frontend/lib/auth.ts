import { betterAuth } from "better-auth";
import { organization } from "better-auth/plugins";
import { Pool } from "pg";
import * as path from "path";

const isPostgres = (url?: string): boolean => {
  if (!url) return false;
  return url.startsWith("postgresql://") || url.startsWith("postgres://");
};

function createDatabaseAdapter() {
  const url =
    process.env.BETTER_AUTH_DATABASE_URL ||
    process.env.DATABASE_URL;

  if (isPostgres(url)) {
    return new Pool({
      connectionString: url,
    });
  }

  // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy-load native module so Postgres deployments never touch it
  const Database = require("better-sqlite3");
  const dbPath = url?.replace(/^sqlite:\/\//, "") || path.resolve(process.cwd(), "..", "anvaya_auth.db");
  return new Database(dbPath);
}

export const auth = betterAuth({
  secret: process.env.BETTER_AUTH_SECRET || "anvaya-local-dev-secret-do-not-use-in-production",
  baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3000",
  basePath: "/api/auth",
  database: createDatabaseAdapter(),
  advanced: {
    defaultCookieAttributes: {
      sameSite: "none",
      secure: true,
    },
  },
  emailAndPassword: {
    enabled: true,
  },
  plugins: [
    organization({
      allowUserToCreateOrganization: true,
    }),
  ],
  trustedOrigins: [
    process.env.BETTER_AUTH_URL || "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
  ],
});
