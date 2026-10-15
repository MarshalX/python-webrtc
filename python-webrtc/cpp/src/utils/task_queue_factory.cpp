//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "task_queue_factory.h"
#include "dispatcher.h"
#include "libwebrtc_thread.h"

#include <api/task_queue/default_task_queue_factory.h>
#include <api/task_queue/task_queue_base.h>

#include <atomic>
#include <utility>

namespace python_webrtc {

  namespace {
    using Queue = std::unique_ptr<webrtc::TaskQueueBase, webrtc::TaskQueueDeleter>;

    // default queues join their own thread when deleted from one of their tasks
    class TaskQueue final : public webrtc::TaskQueueBase {
    public:
      explicit TaskQueue(Queue inner) : _inner(inner.release()), _generation(Forks().load()) {}

      TaskQueue(const TaskQueue &) = delete;
      TaskQueue &operator=(const TaskQueue &) = delete;

      void Delete() override {
        if (!IsCurrent()) {
          // returns once no task runs or can start
          _inner->Delete();
          delete this;
          return;
        }
        _deleted.store(true, std::memory_order_relaxed);
        Dispatcher::Destroy(
            [this]() {
              _inner->Delete();
              delete this;
            },
            _generation);
      }

    protected:
      void PostTaskImpl(absl::AnyInvocable<void() &&> task, const PostTaskTraits & /*traits*/,
                        const webrtc::Location &location) override {
        _inner->PostTask(Wrap(std::move(task)), location);
      }

      void PostDelayedTaskImpl(absl::AnyInvocable<void() &&> task, webrtc::TimeDelta delay,
                               const PostDelayedTaskTraits &traits, const webrtc::Location &location) override {
        if (traits.high_precision) {
          _inner->PostDelayedHighPrecisionTask(Wrap(std::move(task)), delay, location);
        } else {
          _inner->PostDelayedTask(Wrap(std::move(task)), delay, location);
        }
      }

    private:
      ~TaskQueue() override = default;

      absl::AnyInvocable<void() &&> Wrap(absl::AnyInvocable<void() &&> task) {
        return [this, task = std::move(task)]() mutable {
          const CurrentTaskQueueSetter current(this);
          if (!_deleted.load(std::memory_order_relaxed)) {
            std::move(task)();
          }
          // its captures may delete this queue, which must be the current one then
          task = nullptr;
        };
      }

      webrtc::TaskQueueBase *const _inner;
      const int _generation;
      std::atomic<bool> _deleted{false};
    };

    class TaskQueueFactory final : public webrtc::TaskQueueFactory {
    public:
      [[nodiscard]] Queue CreateTaskQueue(absl::string_view name, Priority priority) const override {
        return Queue(new TaskQueue(_default->CreateTaskQueue(name, priority)));
      }

    private:
      std::unique_ptr<webrtc::TaskQueueFactory> _default = webrtc::CreateDefaultTaskQueueFactory();
    };
  } // namespace

  std::unique_ptr<webrtc::TaskQueueFactory> CreateTaskQueueFactory() {
    return std::make_unique<TaskQueueFactory>();
  }

} // namespace python_webrtc
