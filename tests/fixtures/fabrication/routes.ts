import { Router } from "express";
import request from "supertest";

const router = Router();
const store = new Map<string, number>();

router.get("/", async (req, res) => {          // express route registration
  const entry = store.get("k");                 // a plain Map
  const res2 = await request(app).get("/api");  // supertest HTTP verb
  return res.json({ entry, res2 });
});
