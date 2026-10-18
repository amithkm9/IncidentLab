import { validResponse } from "./validation";
import { proofPath } from "./paths";
import type {
  Action,
  Config,
  History,
  InvestigationRecord,
  Mode,
  ProofResponse,
  Recovery,
  RehearsalRecord,
  Scenario,
  Status,
  Strategy,
  Verification,
  Workspace,
} from "../domain";

interface Responses {
  "/api/config": Config;
  "/api/scenarios": Scenario[];
  "/api/status": Status;
  "/api/workspace": Workspace;
  "/api/history": History;
  "/api/inject": Status;
  "/api/investigate": InvestigationRecord;
  "/api/probe": { status: Status; verification: Verification };
  "/api/remediate": Recovery & { status: Status };
  "/api/rehearse": RehearsalRecord;
  "/api/promote": Recovery & { status: Status };
}
interface Requests {
  "/api/inject": { scenario_id: string; seed: number };
  "/api/investigate": { mode: Mode; question: string };
  "/api/probe": { count: number };
  "/api/remediate": { investigation_id: string; action: Action };
  "/api/rehearse": {
    strategy: Strategy;
    max_experiments: number;
    max_actions: number;
    probe_count: number;
  };
  "/api/promote": { rehearsal_id: string; plan_id: string };
}
type ArtifactPath =
  `/api/investigations/${string}` | `/api/rehearsals/${string}`;
type ApiPath = keyof Responses | ArtifactPath;
type ResponseFor<P extends ApiPath> = P extends keyof Responses
  ? Responses[P]
  : P extends `/api/investigations/${string}`
    ? InvestigationRecord
    : P extends `/api/rehearsals/${string}/proof`
      ? ProofResponse
      : RehearsalRecord;
type RequestFor<P extends ApiPath> = P extends keyof Requests
  ? Requests[P]
  : never;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly connectionLost = false,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
async function request(path: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(
      "Could not reach the lab. Check that the server is running, then use Refresh workspace to reconnect.",
      undefined,
      true,
    );
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      `The server returned an unreadable response (${response.status}). Refresh the workspace and retry.`,
    );
  }
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? payload.detail
        : undefined;
    throw new ApiError(
      typeof detail === "string"
        ? detail
        : "The request could not be completed. Check the selected values and try again.",
      response.status,
    );
  }
  if (!validResponse(path, payload)) {
    throw new ApiError(
      "The server returned an unexpected response format. The saved workspace was not replaced. Refresh the workspace before continuing.",
      response.status,
    );
  }
  return payload;
}
/** Validate response shapes before exposing the local API contracts to renderers. */
export async function api<P extends ApiPath>(
  path: P,
  body?: RequestFor<P>,
): Promise<ResponseFor<P>> {
  const payload = await request(
    path,
    body === undefined
      ? { cache: "no-store" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  return payload as ResponseFor<P>;
}
export async function requestRecoveryProof(id: string): Promise<ProofResponse> {
  return (await request(proofPath(id), {
    method: "POST",
  })) as ProofResponse;
}
