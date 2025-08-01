import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faList,
  faFileMedical,
  faFileAlt,
  faCheckCircle,
  faHourglassHalf,
  faExclamationCircle,
  faCalendarAlt,
} from "@fortawesome/free-solid-svg-icons";

interface Job {
  job_id: string;
  timestamp: string;
  filename: string;
  status: string;
}

export function JobsListPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchJobs();
  }, []);

  const fetchJobs = async () => {
    try {
      const response = await fetch(`${import.meta.env.VITE_API_URL}/jobs`);

      if (!response.ok) {
        throw new Error("Failed to fetch jobs");
      }
      const data = await response.json();
      setJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container jobs-page">
      <div className="header">
        <h2>
          <FontAwesomeIcon
            icon={faList}
            style={{ marginRight: "10px", color: "#3b82f6" }}
          />
          Underwriting Jobs
        </h2>
        <div className="header-controls">
          <button onClick={() => navigate("/")} className="nav-button">
            <FontAwesomeIcon icon={faFileMedical} /> Upload New
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading">Loading jobs...</div>
      ) : error ? (
        <div className="error-message">
          {error}
          <button onClick={fetchJobs} className="refresh-button">
            Try Again
          </button>
        </div>
      ) : jobs.length === 0 ? (
        <div className="no-jobs">
          <p>You haven't uploaded any documents yet.</p>
          <button onClick={() => navigate("/")} className="upload-button">
            Upload Your First Document
          </button>
        </div>
      ) : (
        <div className="jobs-list">
          {jobs.map((job: Job) => (
            <div
              key={job.job_id}
              className="job-card"
              onClick={() => navigate(`/jobs/${job.job_id}`)}
            >
              <div className="job-icon">
                <FontAwesomeIcon icon={faFileAlt} />
              </div>
              <div className="job-details">
                <p className="job-filename">{job.filename}</p>
                <p className="job-id">ID: {job.job_id}</p>
              </div>
              <div className="job-meta">
                <div className="job-status">
                  <FontAwesomeIcon
                    icon={
                      job.status === "Completed"
                        ? faCheckCircle
                        : job.status === "In Progress"
                        ? faHourglassHalf
                        : faExclamationCircle
                    }
                  />
                  {job.status}
                </div>
                <div className="job-timestamp">
                  <FontAwesomeIcon icon={faCalendarAlt} />
                  {new Date(job.timestamp).toLocaleString()}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
} 