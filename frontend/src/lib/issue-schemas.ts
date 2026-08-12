import * as z from "zod";

export const issueCreateSchema = z.object({
  title: z.string().min(1, "Title is required").max(200),
  description: z.string().max(2000).optional(),
  category: z.enum([
    "pothole",
    "garbage",
    "debris",
    "waterlogging",
    "broken_streetlight",
    "sewage",
    "road_damage",
  ]),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
});

export type IssueCreateFormData = z.infer<typeof issueCreateSchema>;
