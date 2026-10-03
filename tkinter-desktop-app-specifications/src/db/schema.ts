import { pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";

/**
 * Download log for the Flood Ready Vehicle System source bundle.
 * The desktop application itself uses SQLite (see flood_ready_vehicle_system/);
 * this table only powers the browser preview site.
 */
export const downloadEvents = pgTable("download_events", {
  id: serial("id").primaryKey(),
  artifact: text("artifact").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
