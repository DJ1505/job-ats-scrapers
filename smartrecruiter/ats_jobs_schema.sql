create table public.ats_jobs (
  id serial not null,
  ats_source character varying(50) not null,
  company_slug character varying(255) not null,
  job_id character varying(255) not null,
  job_title text null,
  job_url text null,
  apply_url text null,
  job_description_raw text null,
  job_description_cleaned text null,
  published_date timestamp with time zone null,
  updated_date timestamp with time zone null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  job_location text null,
  city character varying(255) null,
  state character varying(100) null,
  country character varying(100) null,
  postal_code character varying(20) null,
  work_location_type character varying(50) null,
  salary_min integer null,
  salary_max integer null,
  salary_currency character varying(10) null,
  salary_type character varying(20) null,
  equity_offered boolean null,
  visa_sponsorship_available boolean null,
  visa_sponsorship_text text null,
  relocation_assistance boolean null,
  experience_level character varying(50) null,
  years_experience_min integer null,
  management_level character varying(50) null,
  required_skills text[] null,
  preferred_skills text[] null,
  certifications_required text[] null,
  licenses_required text[] null,
  employment_type character varying(50) null,
  job_type character varying(50) null,
  contract_duration character varying(100) null,
  industry_domain character varying(100) null,
  sector character varying(100) null,
  job_function character varying(100) null,
  education_required character varying(50) null,
  degree_field character varying(100) null,
  retirement_401k boolean null,
  work_hours_per_week integer null,
  languages_required text[] null,
  languages_preferred text[] null,
  job_embedding public.vector null,
  processing_status character varying(50) null default 'pending'::character varying,
  ai_extraction_confidence numeric(3, 2) null,
  extraction_errors text[] null,
  raw_data jsonb null,
  sync_status character varying(50) null default 'pending'::character varying,
  error_message text null,
  last_processed timestamp with time zone null,
  company_name character varying(255) null,
  ai_processing_metadata jsonb null,
  job_status character varying(20) null default 'active'::character varying,
  remote_scope character varying(50) null,
  multiple_locations text[] null,
  key_responsibilities text[] null default '{}'::text[],
  project_types text[] null default '{}'::text[],
  skills_embedding public.vector null,
  responsibilities_embedding public.vector null,
  project_context_embedding public.vector null,
  searchable_embedding public.vector null,
  embeddings_generated boolean null default false,
  embeddings_generated_at timestamp with time zone null,
  reprocessing_retry_count integer null default 0,
  constraint ats_jobs_pkey primary key (id),
  constraint unique_ats_job unique (ats_source, company_slug, job_id),
  constraint valid_ai_confidence check (
    (
      (ai_extraction_confidence >= 0.00)
      and (ai_extraction_confidence <= 1.00)
    )
  ),
  constraint valid_job_status check (
    (
      (job_status)::text = any (
        (
          array[
            'active'::character varying,
            'expired'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint valid_remote_scope check (
    (
      (remote_scope)::text = any (
        (
          array[
            'anywhere'::character varying,
            'same_country'::character varying,
            'same_timezone'::character varying,
            null::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint valid_sync_status check (
    (
      (sync_status)::text = any (
        (
          array[
            'pending'::character varying,
            'synced'::character varying,
            'failed'::character varying
          ]
        )::text[]
      )
    )
  ),
  constraint valid_work_location_type check (
    (
      (work_location_type)::text = any (
        (
          array[
            'remote'::character varying,
            'hybrid'::character varying,
            'on-site'::character varying,
            'not_specified'::character varying
          ]
        )::text[]
      )
    )
  )
) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_job_status on public.ats_jobs using btree (job_status) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_remote_scope on public.ats_jobs using btree (remote_scope) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_ats_source on public.ats_jobs using btree (ats_source) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_company_slug on public.ats_jobs using btree (company_slug) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_job_id on public.ats_jobs using btree (job_id) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_processing_status on public.ats_jobs using btree (processing_status) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_sync_status on public.ats_jobs using btree (sync_status) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_work_location_type on public.ats_jobs using btree (work_location_type) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_employment_type on public.ats_jobs using btree (employment_type) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_experience_level on public.ats_jobs using btree (experience_level) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_visa_sponsorship on public.ats_jobs using btree (visa_sponsorship_available) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_city on public.ats_jobs using btree (city) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_state on public.ats_jobs using btree (state) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_country on public.ats_jobs using btree (country) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_published_date on public.ats_jobs using btree (published_date) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_created_at on public.ats_jobs using btree (created_at) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_required_skills on public.ats_jobs using gin (required_skills) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_preferred_skills on public.ats_jobs using gin (preferred_skills) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_languages_required on public.ats_jobs using gin (languages_required) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_extraction_errors on public.ats_jobs using gin (extraction_errors) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_company_name on public.ats_jobs using btree (company_name) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_multiple_locations on public.ats_jobs using gin (multiple_locations) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_key_responsibilities on public.ats_jobs using gin (key_responsibilities) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_project_types on public.ats_jobs using gin (project_types) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_skills_embedding on public.ats_jobs using ivfflat (skills_embedding vector_cosine_ops)
with
  (lists = '100') TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_responsibilities_embedding on public.ats_jobs using ivfflat (responsibilities_embedding vector_cosine_ops)
with
  (lists = '100') TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_project_context_embedding on public.ats_jobs using ivfflat (project_context_embedding vector_cosine_ops)
with
  (lists = '100') TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_searchable_embedding on public.ats_jobs using ivfflat (searchable_embedding vector_cosine_ops)
with
  (lists = '100') TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_embeddings_generated on public.ats_jobs using btree (embeddings_generated) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_sync_gating on public.ats_jobs using btree (processing_status, sync_status, job_status) TABLESPACE pg_default
where
  ((job_status)::text = 'active'::text);

create index IF not exists idx_ats_jobs_processing_jobstatus on public.ats_jobs using btree (processing_status, job_status) TABLESPACE pg_default
where
  ((job_status)::text = 'active'::text);

create index IF not exists idx_ats_jobs_embeddings_gating on public.ats_jobs using btree (
  processing_status,
  embeddings_generated,
  job_status
) TABLESPACE pg_default
where
  ((job_status)::text = 'active'::text);

create index IF not exists idx_ats_jobs_reprocess_gating on public.ats_jobs using btree (
  ai_extraction_confidence,
  processing_status,
  job_status
) TABLESPACE pg_default
where
  ((job_status)::text = 'active'::text);

create index IF not exists idx_ats_jobs_scraped_active_id on public.ats_jobs using btree (id) TABLESPACE pg_default
where
  (
    ((processing_status)::text = 'scraped'::text)
    and ((job_status)::text = 'active'::text)
  );

create index IF not exists idx_ats_jobs_processed_lowconf_active_id on public.ats_jobs using btree (id) TABLESPACE pg_default
where
  (
    ((processing_status)::text = 'processed'::text)
    and ((job_status)::text = 'active'::text)
    and (ai_extraction_confidence < 0.6)
  );

create index IF not exists idx_ats_jobs_company_slug_ats_source on public.ats_jobs using btree (company_slug, ats_source) TABLESPACE pg_default;

create index IF not exists idx_ats_jobs_company_slug_ats_source_active on public.ats_jobs using btree (company_slug, ats_source) TABLESPACE pg_default
where
  ((job_status)::text = 'active'::text);

create trigger trigger_ats_jobs_updated_at BEFORE
update on ats_jobs for EACH row
execute FUNCTION update_ats_jobs_updated_at ();