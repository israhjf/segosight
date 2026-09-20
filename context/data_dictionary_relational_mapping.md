### Task 1: Comprehensive Data Dictionary

**1. Customers / Facilities (`customers.csv`)**
*This file acts as a hybrid table containing both Customer entity data and Facility entity data.*

| Column Name | Inferred Data Type | Nullable | Description/Sample |
| :--- | :--- | :--- | :--- |
| `customer_id` | String | No | Primary key for the corporate entity. (e.g., `CUST-0001`) |
| `customer_name` | String | No | Name of the corporate client. (e.g., `Bonneville Foods`) |
| `facility_id` | String | No | Primary key for the physical site. (e.g., `F-0001`) |
| `facility_name` | String | No | Name of the physical site. (e.g., `Ogden Plant`) |
| `address` | String | No | Street address of the facility. |
| `city` | String | No | City of the facility. |
| `state` | String | No | State abbreviation. (e.g., `UT`) |
| `account_tier` | String | No | Priority level of the client. (e.g., `A`, `B`) |
| `annual_contract_value_usd`| Float | Yes | Revenue value of the contract. (e.g., `128000.0`) |
| `primary_contact_name` | String | No | Main point of contact at the site. (e.g., `Ray Ostler`) |
| `primary_contact_email`| String | Yes | Email for the main contact. |
| `primary_contact_phone`| String | No | Phone number for the contact. |
| `service_frequency` | String | No | Expected visit cadence. (e.g., `weekly`, `biweekly`) |
| `contract_start` | Date (YYYY-MM-DD) | No | Start date of the service agreement. |
| `contract_end` | Date (YYYY-MM-DD) | Yes | End date of the service agreement. |
| `sla_response_hours` | Integer | No | Mandated maximum response time in hours. (e.g., `4`, `24`) |
| `notes` | String | Yes | Administrative notes. |

**2. Physical Equipment (`systems.csv`, `systems_update_2026-09.csv`)**

| Column Name | Inferred Data Type | Nullable | Description/Sample |
| :--- | :--- | :--- | :--- |
| `system_id` | String | No | Primary key for the equipment unit. (e.g., `SYS-0001`) |
| `facility_id` | String | No | Foreign key linking to the facility location. (e.g., `F-0001`) |
| `system_type` | String | No | Category of equipment. (e.g., `steam_boiler`, `cooling_tower`) |
| `description` | String | No | Common name or tag. (e.g., `Fire-tube boiler #1`) |
| `capacity` | String | No | Size rating. (e.g., `250 HP`, `700 ton`) |
| `operating_parameters` | String | No | Engineering parameters. (e.g., `125 psig`, `2-cell crossflow`) |
| `install_date` | Date (YYYY-MM-DD) | Yes | Equipment installation date. |
| `treatment_program` | String | No | Chemistry program applied. (e.g., `BP-STD`, `CT-STD`) |
| `criticality` | String | No | Operational importance. (e.g., `critical`, `important`) |
| `status` | String | No | Active state. (e.g., `active`, `decommissioned`) |
| `notes` | String | Yes | Context regarding the unit's lifecycle or status. |

**3. Water Chemistry (`water_readings.csv`, `water_readings_2026-09.csv`)**

| Column Name | Inferred Data Type | Nullable | Description/Sample |
| :--- | :--- | :--- | :--- |
| `reading_id` | String | No | Primary key for the test event. (e.g., `RD-00001`, `RB-0002`) |
| `timestamp` | Timestamp | No | Date and time of the reading. |
| `system_id` | String | No | Foreign key linking to the tested equipment. (e.g., `SYS-0014`) |
| `collected_by` | String | No | Technician name or automated source. (e.g., `Jenn Fowler`, `BMS export`) |
| `collection_method`| String | No | How the data was gathered. (e.g., `field`, `bms`) |
| `conductivity` | Float | Yes | Micro-siemens reading. (e.g., `2675.0`) |
| `ph` | Float | Yes | pH level. (e.g., `8.8`, `11.0`) |
| `total_hardness` | Float | Yes | Hardness metric. (e.g., `0.7`, `553.0`) |
| `m_alkalinity` | Float | Yes | Alkalinity concentration. |
| `chloride` | Float | Yes | Chloride parts-per-million. |
| `free_halogen` | Float | Yes | Biocide residual. (e.g., `0.49`) |
| `inhibitor_ppm` | Float | Yes | Chemical inhibitor level. |
| `iron` | Float | Yes | Dissolved iron, critical for corrosion tracking. (e.g., `0.17`, `1.35`) |
| `sulfite` | Float | Yes | Sulfite residual. |
| `nitrite` | Float | Yes | Nitrite residual. |
| `microbio_dipslide`| String | Yes | Biological count in powers of 10. (e.g., `10^2`, `10^4`) |
| `units` | String (Key-Value) | No | Unit definitions for the row. (e.g., `cond=uS/cm;nitrite=ppm`) |
| `notes` | String | Yes | Context for the reading, such as lab verifications. |

**4. Service Visits (`service_visits.csv`, `service_visits_2026-09.csv`)**
*Note: The 2026-09 file introduces a `source_system` column (e.g., `FieldFlow`) that legacy data lacks.*

| Column Name | Inferred Data Type | Nullable | Description/Sample |
| :--- | :--- | :--- | :--- |
| `visit_id` | String | No | Primary key for the visit. (e.g., `V-0001`, `FF-1001`) |
| `visit_date` | Date | No | Date of the service. |
| `technician` | String | No | Staff member who executed the visit. (e.g., `Jenn Fowler`, `MW`) |
| `customer_id` | String | No | Foreign key for the corporate client. |
| `facility_id` | String | No | Foreign key for the physical site. |
| `systems_serviced` | String (Delimited)| Yes | Semicolon-separated list of System IDs. (e.g., `SYS-0001;SYS-0002`) |
| `work_performed` | String | Yes | Summary of the task completed. |
| `chemicals_added` | String (Delimited)| Yes | Semicolon-separated list of products and dosages. (e.g., `BW-210 3 gal; BW-305 1 gal`) |
| `visit_status` | String | No | Outcome of the scheduled route. (e.g., `completed`, `missed - rescheduled`) |
| `follow_up_date` | Date | Yes | Planned date to return for open issues. |
| `observations` | String | Yes | Free-text field notes. |

**5. Work Orders (`work_orders.csv`, `work_orders_2026-09.csv`)**

| Column Name | Inferred Data Type | Nullable | Description/Sample |
| :--- | :--- | :--- | :--- |
| `wo_id` | String | No | Primary key for the ticket. (e.g., `WO-0101`) |
| `customer_id` | String | No | Foreign key for the corporate client. |
| `facility_id` | String | No | Foreign key for the physical site. |
| `system_id` | String | Yes | Foreign key for the affected equipment. |
| `created_date` | Date (YYYY-MM-DD) | No | Date the ticket was opened. |
| `priority` | String | No | Urgency level. (e.g., `P1`, `P3`) |
| `status` | String | No | Ticket state. (e.g., `closed`, `resolved`) |
| `owner` | String | No | Employee assigned to the fix. (e.g., `Marcus Webb`) |
| `title` | String | No | Summary of the problem. |
| `description` | String | No | Full details of the failure or required repair. |
| `resolved_date` | Date (YYYY-MM-DD) | Yes | Date the repair was completed. |
| `resolution_notes`| String | Yes | Details of the implemented fix. |
| `estimated_cost_usd`| Float | Yes | Budgeted repair cost. |
| `actual_cost_usd` | Float | Yes | Final repair cost. |

**6. Chemical Inventory (`chemical_inventory.csv`)**

| Column Name | Inferred Data Type | Nullable | Description/Sample |
| :--- | :--- | :--- | :--- |
| `location` | String | No | Physical storage location. (e.g., `Warehouse - SLC`, `Truck - D. Hardy`) |
| `product_code` | String | No | Primary key for the chemical product. (e.g., `CT-770`) |
| `product_name` | String | No | Full name of the chemical. |
| `quantity_on_hand`| Float | No | Current volume in stock. (e.g., `14.0`) |
| `unit` | String | No | Container type. (e.g., `pail`, `jug`) |
| `reorder_level` | Float | No | Threshold triggering a new PO. |
| `avg_monthly_usage`| Float | Yes | Historical consumption rate. |
| `on_order_qty` | Integer | No | Amount currently inbound from suppliers. |
| `expected_delivery_date`| Date (YYYY-MM-DD)| Yes | Expected arrival date of inbound stock. |
| `last_updated` | Date (YYYY-MM-DD)| No | Date of the last manual count. |
| `notes` | String | Yes | Administrative tracking notes. |

---

### Task 2: Relational Mapping (Keys & Cardinality)

**Primary Keys (Explicit & Candidate)**
*   `Facility`: `customers.csv -> facility_id` (Note: `customers.csv` is heavily denormalized; `facility_id` acts as the true row-level identifier, while `customer_id` represents the parent corporate entity).
*   `System`: `systems.csv -> system_id`
*   `Water_Reading`: `water_readings.csv -> reading_id`
*   `Service_Visit`: `service_visits.csv -> visit_id`
*   `Work_Order`: `work_orders.csv -> wo_id`
*   `Chemical_Product`: `chemical_inventory.csv -> product_code` (with `location` acting as a composite key for specific physical inventory records).

**Relationships & Cardinality**
*   **Customer to Facility:** `Customer.customer_id -> Facility.facility_id` **(1:N)**
    *   *A single corporate entity (e.g., Bonneville Foods) can own multiple physical plants.*
*   **Facility to System:** `Facility.facility_id -> System.facility_id` **(1:N)**
    *   *A single plant houses multiple pieces of equipment (boilers, towers).*
*   **System to Water Reading:** `System.system_id -> Water_Reading.system_id` **(1:N)**
    *   *Equipment generates many longitudinal chemistry tests.*
*   **Facility to Service Visit:** `Facility.facility_id -> Service_Visit.facility_id` **(1:N)**
    *   *Technicians visit sites, not individual systems separately.*
*   **System to Work Order:** `System.system_id -> Work_Order.system_id` **(1:N)**
    *   *Repairs are tracked against specific equipment, though nullable if the issue is site-wide.*
*   **Service Visit to System (Many-to-Many):** `Service_Visit.visit_id <-> System.system_id` **(N:M)**
    *   *Currently trapped in a semicolon-delimited string (`systems_serviced`). A formal junction table is required in the Ontology.*
*   **Service Visit to Chemical Product (Many-to-Many):** `Service_Visit.visit_id <-> Chemical_Product.product_code` **(N:M)**
    *   *Currently trapped in a delimited string (`chemicals_added`). Requires a junction table mapping product, dosage amount, and visit.*

---

### Task 3: Data Quality & Anomaly Report

The provided raw data is exceptionally fractured due to a messy CRM migration and varying field practices. If mapped directly into a strict relational database without intermediate cleaning, pipelines will immediately fail.

**1. Severe Format Inconsistencies (Timestamps & Identifiers)**
*   **Date Formats:** The legacy files use standard ISO/SQL formats (`YYYY-MM-DD HH:MM`), whereas the new `FieldFlow` batch (`_2026-09`) uses localized American formats (`M/D/YYYY` and `M/D/YY H:MM`).
*   **Technician Identity Collapse:** Legacy `service_visits` record full names (`Jenn Fowler`), while the `FieldFlow` update exclusively uses initials (`MW`, `TR`).

**2. 1NF Schema Violations (Trapped N:M Relationships)**
*   The `systems_serviced` and `chemicals_added` columns in the Service Visits tables store complex lists as flat strings (e.g., `BW-210 3 gal; BW-305 1 gal`). Any pipeline attempting to aggregate chemical consumption or track specific system touches must parse and unnest these strings before ingestion.
*   The `units` column in the Water Readings table contains concatenated key-value pairs (e.g., `cond=uS/cm;hard=ppm CaCO3`) rather than adhering to column-level typing.

**3. Entity Duplication & Decommissioning**
*   **Customer ID Merges:** The data contains active transactions for `CUST-0019` which is a duplicate of `CUST-0007` (Timpanogos Beverage Co). A pipeline merge rule is required to tie historical data to the surviving ID.
*   **Equipment Swaps:** Boiler `SYS-0006` failed and was replaced by a rental, `SYS-0101`. Trend queries must stitch these IDs together contextually rather than treating them as disconnected islands.

**4. Orphaned Foreign Keys (Lab Reports)**
*   Third-party laboratory uploads inject unmapped sample strings (e.g., `BONF-OGD-B2`) straight into the `system_id` column of `water_readings.csv`. These will violently orphan when joined against `systems.csv` unless intercepted and translated using the manual crosswalk provided in the technician text notes.