BEGIN;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

CREATE TABLE IF NOT EXISTS customers (
  customer_id TEXT PRIMARY KEY, full_name TEXT,
  age INTEGER CHECK (age BETWEEN 18 AND 80), gender TEXT, email TEXT,
  phone TEXT, street_address TEXT, city TEXT, state TEXT, zip_code TEXT,
  registration_date DATE NOT NULL, preferred_channel TEXT
);
CREATE TABLE IF NOT EXISTS products (
  product_id TEXT PRIMARY KEY, product_name TEXT NOT NULL,
  product_category TEXT NOT NULL,
  average_selling_price NUMERIC(14,2) NOT NULL CHECK (average_selling_price >= 0),
  cost_ratio NUMERIC(6,4) NOT NULL CHECK (cost_ratio BETWEEN 0 AND 1),
  unit_cost NUMERIC(14,2) NOT NULL CHECK (unit_cost >= 0),
  is_cost_synthetic BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (unit_cost <= average_selling_price),
  UNIQUE (product_name, product_category)
);
CREATE TABLE IF NOT EXISTS stores (
  store_id TEXT PRIMARY KEY, store_location TEXT NOT NULL UNIQUE,
  store_type TEXT NOT NULL CHECK (store_type IN ('online', 'physical'))
);
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id TEXT PRIMARY KEY, campaign_name TEXT NOT NULL,
  campaign_type TEXT NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL,
  target_segment TEXT, budget NUMERIC(14,2) NOT NULL CHECK (budget >= 0),
  impressions BIGINT NOT NULL CHECK (impressions >= 0),
  clicks BIGINT NOT NULL CHECK (clicks >= 0 AND clicks <= impressions),
  conversions BIGINT NOT NULL CHECK (conversions >= 0 AND conversions <= clicks),
  conversion_rate NUMERIC(8,2) NOT NULL CHECK (conversion_rate BETWEEN 0 AND 100),
  roi NUMERIC(14,2) NOT NULL, CHECK (end_date >= start_date)
);
CREATE TABLE IF NOT EXISTS transactions (
  transaction_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  product_id TEXT REFERENCES products(product_id), product_name TEXT,
  product_category TEXT, quantity INTEGER NOT NULL CHECK (quantity > 0),
  price NUMERIC(14,2) NOT NULL CHECK (price >= 0), transaction_date DATE NOT NULL,
  store_id TEXT REFERENCES stores(store_id), store_location TEXT,
  payment_method TEXT,
  discount_applied NUMERIC(6,2) NOT NULL CHECK (discount_applied BETWEEN 0 AND 100),
  gross_sales NUMERIC(16,2) NOT NULL CHECK (gross_sales >= 0),
  discount_amount NUMERIC(16,2) NOT NULL CHECK (discount_amount >= 0),
  net_sales NUMERIC(16,2) NOT NULL CHECK (net_sales >= 0)
);
CREATE TABLE IF NOT EXISTS interactions (
  interaction_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  channel TEXT NOT NULL, interaction_type TEXT NOT NULL,
  interaction_date DATE NOT NULL, duration NUMERIC(12,2) CHECK (duration >= 0),
  page_or_product TEXT, session_id TEXT
);
CREATE TABLE IF NOT EXISTS support_tickets (
  ticket_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  issue_category TEXT NOT NULL, priority TEXT NOT NULL, submission_date DATE NOT NULL,
  resolution_date DATE, resolution_status TEXT NOT NULL,
  resolution_time_hours NUMERIC(12,2) CHECK (resolution_time_hours >= 0),
  customer_satisfaction_score INTEGER CHECK (customer_satisfaction_score BETWEEN 1 AND 5),
  notes TEXT, CHECK (resolution_date IS NULL OR resolution_date >= submission_date),
  CHECK (resolution_status <> 'resolved' OR resolution_date IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS customer_reviews (
  review_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  product_name TEXT NOT NULL, product_category TEXT NOT NULL, full_name TEXT,
  transaction_date DATE NOT NULL, review_date DATE NOT NULL,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review_title TEXT, review_text TEXT, embedding extensions.vector,
  CHECK (review_date >= transaction_date)
);
CREATE TABLE IF NOT EXISTS inventory (
  inventory_id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL REFERENCES products(product_id),
  store_id TEXT NOT NULL REFERENCES stores(store_id),
  stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
  reorder_level INTEGER NOT NULL CHECK (reorder_level >= 0),
  last_restock_date DATE NOT NULL, snapshot_date DATE NOT NULL,
  needs_reorder BOOLEAN NOT NULL, is_synthetic BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (last_restock_date <= snapshot_date), UNIQUE (product_id, store_id, snapshot_date)
);
CREATE TABLE IF NOT EXISTS expenses (
  expense_id TEXT PRIMARY KEY, expense_date DATE NOT NULL,
  store_id TEXT NOT NULL REFERENCES stores(store_id), expense_category TEXT NOT NULL,
  amount NUMERIC(16,2) NOT NULL CHECK (amount >= 0),
  is_synthetic BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS returns_refunds (
  return_id TEXT PRIMARY KEY,
  transaction_id TEXT NOT NULL UNIQUE REFERENCES transactions(transaction_id),
  customer_id TEXT NOT NULL REFERENCES customers(customer_id), return_date DATE NOT NULL,
  return_quantity INTEGER NOT NULL CHECK (return_quantity > 0), return_reason TEXT NOT NULL,
  refund_status TEXT NOT NULL,
  requested_refund_amount NUMERIC(16,2) NOT NULL CHECK (requested_refund_amount >= 0),
  refund_amount NUMERIC(16,2) CHECK (refund_amount >= 0),
  is_synthetic BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS campaign_attribution (
  attribution_id TEXT PRIMARY KEY,
  transaction_id TEXT NOT NULL UNIQUE REFERENCES transactions(transaction_id),
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id), attribution_date DATE NOT NULL,
  attribution_method TEXT NOT NULL,
  attributed_revenue NUMERIC(16,2) NOT NULL CHECK (attributed_revenue >= 0),
  is_synthetic BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS business_documents (
  document_id BIGSERIAL PRIMARY KEY,
  source_type TEXT NOT NULL CHECK (source_type IN ('customer_review','support_ticket')),
  source_id TEXT NOT NULL, customer_id TEXT REFERENCES customers(customer_id),
  content TEXT NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding_model TEXT NOT NULL, embedding extensions.vector(384) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (source_type, source_id)
);

CREATE TABLE IF NOT EXISTS knowledge_files (
  file_id BIGSERIAL PRIMARY KEY,
  original_filename TEXT NOT NULL,
  file_hash CHAR(64) NOT NULL,
  storage_path TEXT NOT NULL,
  mime_type TEXT,
  file_size BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT knowledge_files_hash_unique UNIQUE (file_hash)
);

CREATE TABLE IF NOT EXISTS unstructured_knowledge_chunks (
  chunk_id BIGSERIAL PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding extensions.vector NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_type, source_id, chunk_index)
);

CREATE OR REPLACE VIEW transaction_profitability AS
WITH completed_refunds AS (
  SELECT transaction_id, SUM(refund_amount) AS refund_amount
  FROM returns_refunds
  WHERE refund_status = 'completed'
  GROUP BY transaction_id
)
SELECT
  t.*,
  p.unit_cost AS estimated_unit_cost,
  CASE WHEN p.product_id IS NULL THEN 'missing_product'
       ELSE 'product_average_ratio' END AS cost_method,
  COALESCE(r.refund_amount, 0) AS completed_refund_amount,
  ROUND(t.net_sales - COALESCE(r.refund_amount, 0), 2) AS recognized_revenue,
  ROUND(t.quantity * p.unit_cost, 2) AS cost_of_goods_sold,
  ROUND(t.net_sales - COALESCE(r.refund_amount, 0) - t.quantity * p.unit_cost, 2)
    AS gross_profit,
  ROUND(
    100 * (t.net_sales - COALESCE(r.refund_amount, 0) - t.quantity * p.unit_cost)
    / NULLIF(t.net_sales - COALESCE(r.refund_amount, 0), 0), 2
  ) AS gross_margin_percent
FROM transactions t
LEFT JOIN products p ON p.product_id = t.product_id
LEFT JOIN completed_refunds r ON r.transaction_id = t.transaction_id;

CREATE OR REPLACE VIEW business_profit_summary AS
WITH sales AS (
  SELECT
    SUM(net_sales) AS net_sales,
    SUM(completed_refund_amount) AS completed_refunds,
    SUM(recognized_revenue) AS recognized_revenue,
    SUM(recognized_revenue) FILTER (WHERE estimated_unit_cost IS NOT NULL)
      AS costed_revenue,
    SUM(cost_of_goods_sold) AS cost_of_goods_sold
  FROM transaction_profitability
), operating AS (
  SELECT COALESCE(SUM(amount), 0) AS operating_expenses FROM expenses
), marketing AS (
  SELECT COALESCE(SUM(budget), 0) AS campaign_spend FROM campaigns
)
SELECT
  ROUND(s.net_sales, 2) AS net_sales_before_refunds,
  ROUND(s.completed_refunds, 2) AS completed_refunds,
  ROUND(s.recognized_revenue, 2) AS refund_adjusted_revenue,
  ROUND(100 * s.costed_revenue / NULLIF(s.recognized_revenue, 0), 2)
    AS cost_coverage_percent,
  ROUND(s.cost_of_goods_sold, 2) AS cost_of_goods_sold,
  ROUND(s.costed_revenue - s.cost_of_goods_sold, 2)
    AS estimated_gross_profit_on_costed_sales,
  ROUND(o.operating_expenses, 2) AS operating_expenses,
  ROUND(m.campaign_spend, 2) AS campaign_spend,
  ROUND(
    s.costed_revenue - s.cost_of_goods_sold
    - o.operating_expenses - m.campaign_spend, 2
  ) AS estimated_operating_profit_on_costed_sales
FROM sales s CROSS JOIN operating o CROSS JOIN marketing m;

CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_product ON transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_transactions_store ON transactions(store_id);
CREATE INDEX IF NOT EXISTS idx_interactions_customer ON interactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_support_customer ON support_tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_customer ON customer_reviews(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_reviews_embedding_hnsw ON customer_reviews
  USING hnsw (embedding extensions.vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_documents_embedding_hnsw ON business_documents
  USING hnsw (embedding extensions.vector_cosine_ops);
COMMIT;
