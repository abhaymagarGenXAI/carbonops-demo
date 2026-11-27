import type { EmissionFactorInput } from "@/types/domain";

const REF = "Indicative starting value (screening level) — replace with the dataset your organisation adopts (DEFRA / IPCC EFDB / India GHG Program) before external reporting";

const f = (category: string, source: string, value: number, unit: string, basis: string): EmissionFactorInput => ({
  source, scope: "Scope 3", value, unit, reference: `${basis}. ${REF}`, validFrom: "2024-01-01", status: "Active", category,
});

/** Starter Scope 3 factors that fit an upstream oil & gas operator: fuel supply chain, freight, travel, commuting, waste, capital goods
 *  and — usually the biggest — use of sold crude and gas. Values are approximate; they are suggestions to edit, not a data source. */
export const SCOPE3_SUGGESTIONS: EmissionFactorInput[] = [
  f("11 Use of sold products", "Combustion of sold crude oil", 3070, "kgCO₂e/tonne", "IPCC 2006 default crude oil ≈ 73.3 tCO₂/TJ × 41.9 GJ/t"),
  f("11 Use of sold products", "Combustion of sold natural gas", 1.95, "kgCO₂e/SCM", "IPCC 2006 default natural gas ≈ 56.1 tCO₂/TJ × ~0.0373 GJ/SCM"),
  f("3 Fuel- and energy-related activities", "Diesel well-to-tank (upstream)", 0.61, "kgCO₂e/litre", "DEFRA well-to-tank, diesel"),
  f("3 Fuel- and energy-related activities", "Electricity transmission & distribution losses", 0.07, "kgCO₂e/kWh", "Grid T&D loss share × grid factor (India)"),
  f("4 Upstream transportation and distribution", "Road freight (heavy goods vehicle)", 0.107, "kgCO₂e/tonne-km", "DEFRA freight, HGV average laden"),
  f("4 Upstream transportation and distribution", "Rail freight", 0.028, "kgCO₂e/tonne-km", "DEFRA freight, rail"),
  f("4 Upstream transportation and distribution", "Sea freight (cargo ship)", 0.016, "kgCO₂e/tonne-km", "DEFRA freight, average cargo ship"),
  f("4 Upstream transportation and distribution", "Air freight", 0.6, "kgCO₂e/tonne-km", "DEFRA freight, air"),
  f("5 Waste generated in operations", "Waste to landfill (mixed)", 446, "kgCO₂e/tonne", "DEFRA waste disposal, landfill"),
  f("5 Waste generated in operations", "Waste recycled", 21, "kgCO₂e/tonne", "DEFRA waste disposal, recycling"),
  f("5 Waste generated in operations", "Waste incinerated", 21, "kgCO₂e/tonne", "DEFRA waste disposal, combustion"),
  f("6 Business travel", "Air travel – domestic", 0.246, "kgCO₂e/passenger-km", "DEFRA business travel, domestic flight"),
  f("6 Business travel", "Air travel – long haul economy", 0.148, "kgCO₂e/passenger-km", "DEFRA business travel, long-haul economy"),
  f("6 Business travel", "Rail travel", 0.035, "kgCO₂e/passenger-km", "DEFRA business travel, national rail"),
  f("6 Business travel", "Taxi / cab", 0.149, "kgCO₂e/km", "DEFRA business travel, regular taxi"),
  f("7 Employee commuting", "Commuting – bus", 0.1, "kgCO₂e/passenger-km", "DEFRA, local bus average"),
  f("7 Employee commuting", "Commuting – car (average)", 0.17, "kgCO₂e/km", "DEFRA, average car"),
  f("7 Employee commuting", "Commuting – two-wheeler", 0.08, "kgCO₂e/km", "DEFRA, motorcycle average"),
  f("2 Capital goods", "Steel (capital equipment, by weight)", 2, "kgCO₂e/kg", "World Steel Association / ICE database, average steel"),
  f("1 Purchased goods and services", "General purchased services (spend-based)", 0.0035, "kgCO₂e/INR", "Screening-level spend-based factor (≈ 0.3 kgCO₂e/USD)"),
];
