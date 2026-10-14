//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_UTILS_TASK_QUEUE_FACTORY_H_
#define PYTHON_WEBRTC_UTILS_TASK_QUEUE_FACTORY_H_

#include <api/task_queue/task_queue_factory.h>

#include <memory>

namespace python_webrtc {

  // libwebrtc's default queues, deletable from their own tasks
  std::unique_ptr<webrtc::TaskQueueFactory> CreateTaskQueueFactory();

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_UTILS_TASK_QUEUE_FACTORY_H_
