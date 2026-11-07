# Volcengine Seedream API Notes

## Fixed Values

- host: `visual.volcengineapi.com`
- endpoint: `https://visual.volcengineapi.com`
- service: `cv`
- region: `cn-north-1`
- version: `2022-08-31`
- submit action: `CVSync2AsyncSubmitTask`
- result action: `CVSync2AsyncGetResult`
- req_key: `high_aes_general_v30l_zt2i`

## Submit Request Fields

- required:
  - `req_key`
  - `prompt`
- common optional:
  - `use_pre_llm`
  - `seed`
  - `scale`
  - `width`
  - `height`

The service returns `data.task_id` when `code=10000`.

## Result Request Fields

- required:
  - `req_key`
  - `task_id`
- optional:
  - `req_json`

Useful `req_json` fields:

- `return_url`
- `logo_info`
- `aigc_meta`

## Result Status Values

- `in_queue`
- `generating`
- `done`
- `not_found`
- `expired`

## Practical Notes

- URL results expire after 24 hours.
- The service returns one image per successful generation call.
- Prompt text containing exact visible lettering should keep the target text in double quotes when possible.
- The docs recommend image sizes around 1.3K for a good quality-performance balance.
